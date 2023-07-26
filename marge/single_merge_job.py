# pylint: disable=too-many-locals,too-many-branches,too-many-statements
import logging as log
import time
from datetime import datetime

from . import git, gitlab
from .commit import Commit
from .job import CannotMerge, GitLabRebaseResultMismatch, MergeJob, SkipMerge

from .merge_request import MergeRequest
from .project import Project


class SingleMergeJob(MergeJob):

    def __init__(self, *, api, user, project, repo, options, merge_request):
        super().__init__(api=api, user=user, project=project, repo=repo, options=options)
        self._merge_request = merge_request
        self._options = options

    def execute(self):
        merge_request = self._merge_request

        log.info('Processing !%s - %r', merge_request.iid, merge_request.title)

        try:
            approvals = merge_request.fetch_approvals()
            self.update_merge_request_and_accept(approvals)
            log.info('Successfully merged !%s.', merge_request.info['iid'])
        except SkipMerge as err:
            log.warning("Skipping MR !%s: %s", merge_request.info['iid'], err.reason)
        except CannotMerge as err:
            message = "I couldn't merge this branch: %s" % err.reason
            log.warning(message)
            self.unassign_from_mr(merge_request)
            merge_request.comment(message)
        except git.GitError:
            log.exception('Unexpected Git error')
            merge_request.comment('Something seems broken on my local git repo; check my logs!')
            raise
        except Exception:
            log.exception('Unexpected Exception')
            merge_request.comment("I'm broken on the inside, please somebody fix me... :cry:")
            self.unassign_from_mr(merge_request)
            raise

    def update_merge_request_and_accept(self, approvals):
        api = self._api
        merge_request: MergeRequest = self._merge_request
        updated_into_up_to_date_target_branch = False

        while not updated_into_up_to_date_target_branch:
            self.ensure_mergeable_mr(merge_request)
            source_project, source_repo_url, _ = self.fetch_source_project(merge_request)
            target_project = self.get_target_project(merge_request)

            target_sha, actual_sha = self.get_mergerequest_branches_sha(merge_request, source_repo_url)

            source_synced_with_target = self._repo.ref_contains_specified_commit(
                source_repo_url, merge_request.source_branch, target_sha)
            if not source_synced_with_target:
                try:
                    actual_sha = self.synchronize_with_target(api, source_project, merge_request,
                                                              source_repo_url, approvals)
                except RequireRetryException:
                    continue

            if target_project.only_allow_merge_if_pipeline_succeeds:
                self.wait_for_ci_to_pass(merge_request, actual_sha)
                time.sleep(2)

            self.wait_for_merge_status_to_resolve(merge_request)

            self.ensure_mergeable_mr(merge_request)

            try:
                ret = merge_request.accept(
                    remove_branch=merge_request.force_remove_source_branch,
                    sha=actual_sha,
                    merge_when_pipeline_succeeds=bool(target_project.only_allow_merge_if_pipeline_succeeds),
                )
            except gitlab.NotAcceptable as err:
                new_target_sha = Commit.last_on_branch(self._project.id, merge_request.target_branch, api).id
                # target_branch has moved under us since we updated, just try again
                if new_target_sha != target_sha:
                    log.info('Someone was naughty and by-passed marge')
                    merge_request.comment(
                        "My job would be easier if people didn't jump the queue and push directly... *sigh*"
                    )
                    continue
                # otherwise the source branch has been pushed to or something
                # unexpected went wrong in either case, we expect the user to
                # explicitly re-assign to marge (after resolving potential
                # problems)
                raise CannotMerge('Merge request was rejected by GitLab: %r' % err.error_message) from err
            except gitlab.Unauthorized as err:
                log.warning('Unauthorized!')
                raise CannotMerge('My user cannot accept merge requests!') from err
            except gitlab.NotFound as ex:
                log.warning('Not Found!: %s', ex)
                merge_request.refetch_info()
                if merge_request.state == 'merged':
                    # someone must have hit "merge when build succeeds" and we lost the race,
                    # the branch is gone and we got a 404. Anyway, our job here is done.
                    # (see #33)
                    updated_into_up_to_date_target_branch = True
                else:
                    log.warning('For the record, merge request state is %r', merge_request.state)
                    raise
            except gitlab.MethodNotAllowed as ex:
                log.warning('Not Allowed!: %s', ex)
                merge_request.refetch_info()
                if merge_request.work_in_progress:
                    raise CannotMerge(
                        'The request was marked as WIP as I was processing it (maybe a WIP commit?)'
                    ) from ex
                if merge_request.state == 'reopened':
                    raise CannotMerge(
                        'GitLab refused to merge this branch. I suspect that a Push Rule or a git-hook '
                        'is rejecting my commits; maybe my email needs to be white-listed?'
                    ) from ex
                if merge_request.state == 'closed':
                    raise CannotMerge(
                        'Someone closed the merge request while I was attempting to merge it.'
                    ) from ex
                if merge_request.state == 'merged':
                    # We are not covering any observed behaviour here, but if at this
                    # point the request is merged, our job is done, so no need to complain
                    log.info('Merge request is already merged, someone was faster!')
                    updated_into_up_to_date_target_branch = True
                else:
                    raise CannotMerge(
                        "Gitlab refused to merge this request and I don't know why!" + (
                            " Maybe you have unresolved discussions?"
                            if self._project.only_allow_merge_if_all_discussions_are_resolved else ""
                        )
                    ) from ex
            except gitlab.ApiError as err:
                log.exception('Unanticipated ApiError from GitLab on merge attempt')
                raise CannotMerge('had some issue with GitLab, check my logs...') from err
            else:
                self.wait_for_branch_to_be_merged()
                updated_into_up_to_date_target_branch = True

    def get_mergerequest_branches_sha(self, merge_request: MergeRequest, source_repo_url):
        self._repo.fetch("origin")
        if source_repo_url:
            self._repo.fetch("source", source_repo_url)
            actual_sha = self._repo.get_commit_hash(f"source/{merge_request.source_branch}")
        else:
            actual_sha = self._repo.get_commit_hash(f"origin/{merge_request.source_branch}")

        target_sha = self._repo.get_commit_hash(f"origin/{merge_request.target_branch}")

        return target_sha, actual_sha

    def synchronize_with_target(self, api: gitlab.Api, source_project: Project,  merge_request: MergeRequest,
                                source_repo_url: str, approvals):
        try:
            # NB. this will be a no-op if there is nothing to update/rewrite
            target_sha, _updated_sha, actual_sha = self.update_from_target_branch_and_push(
                merge_request,
                source_repo_url=source_repo_url,
            )
        except GitLabRebaseResultMismatch as ex:
            log.info("Gitlab rebase didn't give expected result")
            merge_request.comment("Someone skipped the queue! Will have to try again...")
            raise RequireRetryException from ex

        if _updated_sha == actual_sha and self._options.guarantee_final_pipeline:
            log.info('No commits on target branch to fuse, triggering pipeline...')
            merge_request.comment("jenkins retry")
            time.sleep(30)

        log.info(
            'Commit id to merge %r into: %r (updated sha: %r)',
            actual_sha,
            target_sha,
            _updated_sha
        )
        time.sleep(5)

        sha_now = Commit.last_on_branch(source_project.id, merge_request.source_branch, api).id
        # Make sure no-one managed to race and push to the branch in the
        # meantime, because we're about to impersonate the approvers, and
        # we don't want to approve unreviewed commits
        if sha_now != actual_sha:
            raise CannotMerge('Someone pushed to branch while we were trying to merge')

        self.maybe_reapprove(merge_request, approvals)

        return actual_sha

    def wait_for_branch_to_be_merged(self):
        merge_request = self._merge_request
        time_0 = datetime.utcnow()
        waiting_time_in_secs = 10

        while datetime.utcnow() - time_0 < self._merge_timeout:
            merge_request.refetch_info()

            if merge_request.state == 'merged':
                return  # success!
            if merge_request.state == 'closed':
                raise CannotMerge('someone closed the merge request while merging!')
            assert merge_request.state in ('opened', 'reopened', 'locked'), merge_request.state

            log.info('Giving %s more secs for !%s to be merged...', waiting_time_in_secs, merge_request.iid)
            time.sleep(waiting_time_in_secs)

        raise CannotMerge('It is taking too long to see the request marked as merged!')


class RequireRetryException(Exception):
    pass
