import logging as log
import time
from collections import namedtuple
from datetime import datetime, timedelta

from . import git, gitlab
from .commit import Commit
from .interval import IntervalUnion
from .project import Project
from .user import User

class MergeJob(object):
    def __init__(self, api, user, project, merge_request, repo, options):
        self._api = api
        self._user = user
        self._project = project
        self._merge_request = merge_request
        self._repo = repo
        self._options = options
        self.max_merge_waiting_time = timedelta(minutes=5)

    @property
    def repo(self):
        return self._repo

    @property
    def opts(self):
        return self._options

    def execute(self):
        merge_request = self._merge_request

        log.info('Processing !%s - %r', merge_request.iid, merge_request.title)

        if self._user.id != merge_request.assignee_id:
            log.info('It is not assigned to us anymore! -- SKIPPING')
            return

        state = merge_request.state
        if state not in ('opened', 'reopened'):
            if state in ('merged', 'closed'):
                log.info('The merge request is already %s!', state)
            else:
                log.info('The merge request is an unknown state: %r', state)
                merge_request.comment('The merge request seems to be in a weird state: %r!', state)
            self.unassign_from_mr(merge_request)
            return

        try:
            if self.during_merge_embargo():
                log.info('Merge embargo! -- SKIPPING')
                return

            approvals = merge_request.fetch_approvals()
            self.rebase_and_accept(approvals)
            log.info('Successfully merged !%s.', merge_request.info['iid'])
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
            raise

    def rebase_and_accept(self, approvals):
        api = self._api
        merge_request = self._merge_request
        rebased_into_up_to_date_target_branch = False

        while not rebased_into_up_to_date_target_branch:
            if merge_request.work_in_progress:
                raise CannotMerge("Sorry, I can't merge requests marked as Work-In-Progress!")
            if merge_request.squash and self.opts.requests_commit_tagging:
                raise CannotMerge(
                    "Sorry, merging requests marked as auto-squash would ruin my commit tagging!"
                )
            approvals.refetch_info()
            if not approvals.sufficient:
                raise CannotMerge(
                    'Insufficient approvals '
                    '(have: {0.approver_usernames} missing: {0.approvals_left})'.format(approvals)
                )
            source_project = (
                self._project if merge_request.source_project_id == self._project.id else
                Project.fetch_by_id(merge_request.source_project_id, api=api)
            )

            should_add_tested = self.opts.add_tested and self._project.only_allow_merge_if_pipeline_succeeds
            tested_by = (
                ['{0._user.name} <{1.web_url}>'.format(self, merge_request)] if should_add_tested
                else None
            )
            reviewers = (
                _get_reviewer_names_and_emails(approvals=approvals, api=api) if self.opts.add_reviewers
                else None
            )
            source_repo_url = None if source_project is self._project else source_project.ssh_url_to_repo
            # NB. this will be a no-op if there is nothing to rebase/rewrite
            target_sha, _rebased_sha, actual_sha = push_rebased_and_rewritten_version(
                repo=self.repo,
                source_branch=merge_request.source_branch,
                target_branch=merge_request.target_branch,
                source_repo_url=source_repo_url,
                reviewers=reviewers,
                tested_by=tested_by,
            )
            log.info('Commit id to merge %r (into: %r)', actual_sha, target_sha)
            time.sleep(5)

            if source_project.only_allow_merge_if_pipeline_succeeds:
                self.wait_for_ci_to_pass(source_project.id, actual_sha)
                log.info('CI passed!')
                time.sleep(2)

            sha_now = Commit.last_on_branch(source_project.id, merge_request.source_branch, api).id
            # Make sure no-one managed to race and push to the branch in the
            # meantime, because we're about to impersonate the approvers, and
            # we don't want to approve unreviewed commits
            if sha_now != actual_sha:
                raise CannotMerge('Someone pushed to branch while we were trying to merge')
            # Re-approve the merge request, in case us pushing it has removed
            # approvals. Note that there is a bit of a race; effectively
            # approval can't be withdrawn after we've pushed (resetting
            # approvals) and CI runs.
            if self.opts.reapprove:
                # approving is not idempotent, so we need to check first that there are no approvals,
                # otherwise we'll get a failure on trying to re-instate the previous approvals
                current_approvals = merge_request.fetch_approvals()
                if not current_approvals.sufficient:
                    approvals.reapprove()
            try:
                merge_request.accept(remove_branch=True, sha=actual_sha)
            except gitlab.NotAcceptable as err:
                new_target_sha = Commit.last_on_branch(self._project.id, merge_request.target_branch, api).id
                # target_branch has moved under us since we rebased, just try again
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
                raise CannotMerge('Merge request was rejected by GitLab: %r' % err.error_message)
            except gitlab.Unauthorized:
                log.warning('Unauthorized!')
                raise CannotMerge('My user cannot accept merge requests!')
            except gitlab.NotFound as e:
                log.warning('Not Found!: %s', e)
                merge_request.refetch_info()
                if merge_request.state == 'merged':
                    # someone must have hit "merge when build succeeds" and we lost the race,
                    # the branch is gone and we got a 404. Anyway, our job here is done.
                    # (see #33)
                    rebased_into_up_to_date_target_branch = True
                else:
                    log.warning('For the record, merge request state is %r', merge_request.state)
                    raise
            except gitlab.MethodNotAllowed as e:
                log.warning('Not Allowed!: %s', e)
                merge_request.refetch_info()
                if merge_request.work_in_progress:
                    raise CannotMerge(
                        'The request was marked as WIP as I was processing it (maybe a WIP commit?)'
                    )
                elif merge_request.state == 'reopened':
                    raise CannotMerge(
                        'GitLab refused to merge this branch. I suspect that a Push Rule or a git-hook '
                        'is rejecting my commits; maybe my email needs to be white-listed?'
                    )
                elif merge_request.state == 'closed':
                    raise CannotMerge('Someone closed the merge request while I was attempting to merge it.')
                elif merge_request.state == 'merged':
                    # We are not covering any observed behaviour here, but if at this
                    # point the request is merged, our job is done, so no need to complain
                    log.info('Merge request is already merged, someone was faster!')
                    rebased_into_up_to_date_target_branch = True
                else:
                    raise CannotMerge("Gitlab refused to merge this request and I don't know why!")
            except gitlab.ApiError:
                log.exception('Unanticipated ApiError from Gitlab on merge attempt')
                raise CannotMerge('had some issue with gitlab, check my logs...')
            else:
                self.wait_for_branch_to_be_merged()
                rebased_into_up_to_date_target_branch = True

    def wait_for_ci_to_pass(self, source_project_id, commit_sha):
        api = self._api
        time_0 = datetime.utcnow()
        waiting_time_in_secs = 10

        while datetime.utcnow() - time_0 < self._options.max_ci_waiting_time:
            ci_status = Commit.fetch_by_id(source_project_id, commit_sha, api).status
            if ci_status == 'success':
                return

            if ci_status == 'failed':
                raise CannotMerge('CI failed!')

            if ci_status == 'canceled':
                raise CannotMerge('Someone canceled the CI')

            if ci_status not in ('pending', 'running'):
                log.warning('Suspicious build status: %r', ci_status)

            log.info('Waiting for %s secs before polling CI status again', waiting_time_in_secs)
            time.sleep(waiting_time_in_secs)

        raise CannotMerge('CI is taking too long')

    def wait_for_branch_to_be_merged(self):
        merge_request = self._merge_request
        time_0 = datetime.utcnow()
        waiting_time_in_secs = 10

        while datetime.utcnow() - time_0 < self.max_merge_waiting_time:
            merge_request.refetch_info()

            if merge_request.state == 'merged':
                return  # success!
            if merge_request.state == 'closed':
                raise CannotMerge('someone closed the merge request while merging!')
            assert merge_request.state in ('opened', 'reopened'), merge_request.state

            log.info('Giving %s more secs for !%s to be merged...', waiting_time_in_secs, merge_request.iid)
            time.sleep(waiting_time_in_secs)

        raise CannotMerge('It is taking too long to see the request marked as merged!')

    def unassign_from_mr(self, mr):
        author_id = mr.author_id
        if author_id != self._user.id:
            mr.assign_to(author_id)
        else:
            mr.unassign()

    def during_merge_embargo(self):
        now = datetime.utcnow()
        return self.opts.embargo.covers(now)

def push_rebased_and_rewritten_version(
        repo,
        source_branch,
        target_branch,
        source_repo_url=None,
        reviewers=None,
        tested_by=None,
):
    """Rebase `target_branch` into `source_branch`, optionally add trailers and push.

    Parameters
    ----------
    source_branch
       The branch we want to rebase to.
    target_branch
       The branch we want to rebase from.
    source_repo_url
       The url of the repo we want to push the changes to (or `None` if it's the
       same repo for both `source_branch` and `target_branch`).
    reviewers
       A list, possibly empty, if we should add reviewer information or `None`
       if we should not add reviewer information. The difference between
       ``None`` and ``[]``  (or another list) is that with ``None`` we leave existing
       Reviewed-by: trailers in place  whereas with a list argument we replace them.
    tested_by
       A list like ``["User Name <u.name@invalid.com>", ...]`` or `None`. ``None`` means
       existing Tested-by lines will be left alone, otherwise they will be replaced.

    Returns
    -------
    (sha_of_target_branch, sha_after_rebase, sha_after_rewrite)
    """
    assert source_repo_url != repo.remote_url
    if source_repo_url is None and source_branch == target_branch:
        raise CannotMerge('source and target branch seem to coincide!')

    branch_rebased = branch_rewritten = changes_pushed = False
    try:
        rewritten_sha = rebased_sha = repo.rebase(
            branch=source_branch,
            new_base=target_branch,
            source_repo_url=source_repo_url
        )
        branch_rebased = True
        if reviewers is not None:
            rewritten_sha = repo.tag_with_trailer(
                trailer_name='Reviewed-by',
                trailer_values=reviewers,
                branch=source_branch,
                start_commit='origin/' + target_branch,
            )
        if tested_by is not None:
            rewritten_sha = repo.tag_with_trailer(
                trailer_name='Tested-by',
                trailer_values=tested_by,
                branch=source_branch,
                start_commit=source_branch+'^'
            )
        branch_rewritten = True
        repo.push_force(source_branch, source_repo_url)
        changes_pushed = True
    except git.GitError:
        if not branch_rebased:
            raise CannotMerge('got conflicts while rebasing, your problem now...')
        if not branch_rewritten:
            raise CannotMerge('failed on filter-branch; check my logs!')
        if not changes_pushed:
            raise CannotMerge('failed to push rebased changes, check my logs!')

        raise
    else:
        target_sha = repo.get_commit_hash('origin/' + target_branch)
        return target_sha, rebased_sha, rewritten_sha
    finally:
        # A failure to clean up probably means something is fucked with the git repo
        # and likely explains any previous failure, so it will better to just
        # raise a GitError
        if source_branch != 'master':
            repo.remove_branch(source_branch)
        else:
            assert source_repo_url is not None

def _get_reviewer_names_and_emails(approvals, api):
    """Return a list ['A. Prover <a.prover@example.com', ...]` for `merge_request.`"""

    uids = approvals.approver_ids
    return ['{0.name} <{0.email}>'.format(User.fetch_by_id(uid, api)) for uid in uids]


_job_options = [
    'add_tested', 'add_reviewers', 'reapprove', 'embargo', 'max_ci_waiting_time',
]

class MergeJobOptions(namedtuple('MergeJobOptions', _job_options)):
    __slots__ = ()

    @property
    def requests_commit_tagging(self):
        return self.add_tested or self.add_reviewers

    @classmethod
    def default(
            cls,
            add_tested=False, add_reviewers=False, reapprove=False,
            embargo=None, max_ci_waiting_time=None,
    ):
        embargo = embargo or IntervalUnion.empty()
        max_ci_waiting_time = max_ci_waiting_time or timedelta(minutes=15)
        return cls(
            add_tested=add_tested,
            add_reviewers=add_reviewers,
            reapprove=reapprove,
            embargo=embargo,
            max_ci_waiting_time=max_ci_waiting_time,
        )


class CannotMerge(Exception):
    @property
    def reason(self):
        args = self.args
        if not args:
            return 'Unknown reason!'

        return args[0]
