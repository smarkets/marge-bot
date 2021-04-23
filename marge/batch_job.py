# pylint: disable=too-many-branches,too-many-statements,arguments-differ
import logging as log
import time

from . import git
from . import gitlab
from .commit import Commit
from .job import MergeJob, CannotMerge, SkipMerge
from .merge_request import MergeRequest
from .pipeline import Pipeline


class CannotBatch(Exception):
    pass


class BatchMergeJob(MergeJob):
    BATCH_BRANCH_NAME = 'marge_bot_batch_merge_job'

    def __init__(self, *, api, user, project, repo, options, merge_requests):
        super().__init__(api=api, user=user, project=project, repo=repo, options=options)
        self._merge_requests = merge_requests

    def remove_batch_branch(self):
        log.info('Removing local batch branch')
        try:
            self._repo.remove_branch(BatchMergeJob.BATCH_BRANCH_NAME)
        except git.GitError:
            pass

    def close_batch_mr(self):
        log.info('Closing batch MRs')
        params = {
            'author_id': self._user.id,
            'labels': BatchMergeJob.BATCH_BRANCH_NAME,
            'state': 'opened',
            'order_by': 'created_at',
            'sort': 'desc',
        }
        batch_mrs = MergeRequest.search(
            api=self._api,
            project_id=self._project.id,
            params=params,
        )
        for batch_mr in batch_mrs:
            log.info('Closing batch MR !%s', batch_mr.iid)
            batch_mr.close()

    def create_batch_mr(self, target_branch):
        self.push_batch()
        log.info('Creating batch MR')
        params = {
            'source_branch': BatchMergeJob.BATCH_BRANCH_NAME,
            'target_branch': target_branch,
            'title': 'Marge Bot Batch MR - DO NOT TOUCH',
            'labels': BatchMergeJob.BATCH_BRANCH_NAME,
        }
        batch_mr = MergeRequest.create(
            api=self._api,
            project_id=self._project.id,
            params=params,
        )
        log.info('Batch MR !%s created', batch_mr.iid)
        return batch_mr

    def get_mrs_with_common_target_branch(self, target_branch):
        log.info('Filtering MRs with target branch %s', target_branch)
        return [
            merge_request for merge_request in self._merge_requests
            if merge_request.target_branch == target_branch
        ]

    def ensure_mergeable_mr(self, merge_request, skip_ci=False):
        super().ensure_mergeable_mr(merge_request)

        if self._project.only_allow_merge_if_pipeline_succeeds and not skip_ci:
            ci_status = self.get_mr_ci_status(merge_request)
            if ci_status != 'success':
                raise CannotBatch('This MR has not passed CI.')

    def get_mergeable_mrs(self, merge_requests):
        log.info('Filtering mergeable MRs')
        mergeable_mrs = []
        for merge_request in merge_requests:
            try:
                self.ensure_mergeable_mr(merge_request)
            except (CannotBatch, SkipMerge) as ex:
                log.warning('Skipping unbatchable MR: "%s"', ex)
            except CannotMerge as ex:
                log.warning('Skipping unmergeable MR: "%s"', ex)
                self.unassign_from_mr(merge_request)
                merge_request.comment("I couldn't merge this branch: {}".format(ex))
            else:
                mergeable_mrs.append(merge_request)
        return mergeable_mrs

    def push_batch(self):
        log.info('Pushing batch branch')
        self._repo.push(BatchMergeJob.BATCH_BRANCH_NAME, force=True)

    def ensure_mr_not_changed(self, merge_request):
        log.info('Ensuring MR !%s did not change', merge_request.iid)
        changed_mr = MergeRequest.fetch_by_iid(
            merge_request.project_id,
            merge_request.iid,
            self._api,
        )
        error_message = 'The {} changed whilst merging!'
        for attr in ('source_branch', 'source_project_id', 'target_branch', 'target_project_id', 'sha'):
            if getattr(changed_mr, attr) != getattr(merge_request, attr):
                raise CannotMerge(error_message.format(attr.replace('_', ' ')))

    def merge_batch(self, target_branch, source_branch, no_ff=False, source_repo_url=None, local=False):
        if no_ff:
            return self._repo.merge(
                    target_branch,
                    source_branch,
                    '--no-ff',
                    source_repo_url,
            )

        return self._repo.fast_forward(
            target_branch,
            source_branch,
            local=local
        )

    def update_merge_request(
        self,
        merge_request,
        source_repo_url=None,
    ):
        log.info('Fusing MR !%s', merge_request.iid)
        approvals = merge_request.fetch_approvals()

        _, _, actual_sha = self.update_from_target_branch_and_push(
            merge_request,
            source_repo_url=source_repo_url,
            skip_ci=self._options.skip_ci_batches,
        )

        sha_now = Commit.last_on_branch(
            merge_request.source_project_id, merge_request.source_branch, self._api,
        ).id
        log.info('update_merge_request: sha_now (%s), actual_sha (%s)', sha_now, actual_sha)
        # Make sure no-one managed to race and push to the branch in the
        # meantime, because we're about to impersonate the approvers, and
        # we don't want to approve unreviewed commits
        if sha_now != actual_sha:
            raise CannotMerge('Someone pushed to branch while we were trying to merge')

        # As we're not using the API to merge the individual MR, we don't strictly need to reapprove it.
        # However, it's a little weird to look at the merged MR to find it has no approvals,
        # so let's do it anyway.
        self.maybe_reapprove(merge_request, approvals)
        return sha_now

    def accept_mr(
        self,
        merge_request,
        expected_remote_target_branch_sha,
        source_repo_url=None,
    ):
        log.info('Accept MR !%s', merge_request.iid)

        # Make sure latest commit in remote <target_branch> is the one we tested against
        new_target_sha = Commit.last_on_branch(self._project.id, merge_request.target_branch, self._api).id
        if new_target_sha != expected_remote_target_branch_sha:
            raise CannotBatch('Someone was naughty and by-passed marge')

        log.debug("batch: accept_mr: self.update_merge_request")
        # Rebase and apply the trailers
        self.update_merge_request(
            merge_request,
            source_repo_url=source_repo_url,
        )

        log.debug("batch: accept_mr: self.merge_batch")
        final_sha = self.merge_batch(
            merge_request.target_branch,
            merge_request.source_branch,
            self._options.use_no_ff_batches,
            source_repo_url,
            local=True  # since we're merging multiple MRs from forks, local needs to be used
        )
        log.debug("batch: accept_mr: self._repo.push")
        # Don't force push in case the remote has changed.
        self._repo.push(merge_request.target_branch, force=False)

        # delay in case Gitlab is slow to respond
        waiting_time_in_secs = 10
        log.debug('Waiting for %s secs for Gitlab to start CI after push', waiting_time_in_secs)
        time.sleep(waiting_time_in_secs)

        # At this point Gitlab should have recognised the MR as being accepted.
        log.info('Successfully merged MR !%s', merge_request.iid)

        pipelines = Pipeline.pipelines_by_branch(
            api=self._api,
            project_id=merge_request.source_project_id,
            branch=merge_request.source_branch,
            status='running',
        )

        log.debug("batch: accept_mr: canceling pipelines in Gitlab")
        # NOTE: this might not abort the pipeline running in external CI, it merely disconnects the pipeline
        for pipeline in pipelines:
            pipeline.cancel()

        return final_sha

    def execute(self):
        # Cleanup previous batch work
        self.remove_batch_branch()
        self.close_batch_mr()

        target_branch = self._merge_requests[0].target_branch
        merge_requests = self.get_mrs_with_common_target_branch(target_branch)
        merge_requests = self.get_mergeable_mrs(merge_requests)

        if len(merge_requests) <= 1:
            # Either no merge requests are ready to be merged, or there's only one for this target branch.
            # Let's raise an error to do a basic job for these cases.
            raise CannotBatch('not enough ready merge requests')

        self._repo.fetch('origin')

        # Save the sha of remote <target_branch> so we can use it to make sure
        # the remote wasn't changed while we're testing against it
        remote_target_branch_sha = self._repo.get_commit_hash('origin/%s' % target_branch)

        self._repo.checkout_branch(target_branch, 'origin/%s' % target_branch)
        self._repo.checkout_branch(BatchMergeJob.BATCH_BRANCH_NAME, 'origin/%s' % target_branch)

        batch_mr = self.create_batch_mr(
            target_branch=target_branch,
        )
        batch_mr_sha = batch_mr.sha

        # delay in case Gitlab is slow to respond
        waiting_time_in_secs = 20
        log.debug('Waiting for %s secs for MR !%s to get status update', waiting_time_in_secs, batch_mr.iid)
        time.sleep(waiting_time_in_secs)

        working_merge_requests = []

        for merge_request in merge_requests:
            try:
                _, source_repo_url, merge_request_remote = self.fetch_source_project(merge_request)
                self._repo.checkout_branch(
                    merge_request.source_branch,
                    '%s/%s' % (merge_request_remote, merge_request.source_branch),
                )

                if self._options.use_merge_commit_batches:
                    # Rebase and apply the trailers before running the batch MR
                    actual_sha = self.update_merge_request(
                        merge_request,
                        source_repo_url=source_repo_url,
                    )
                    # Update <batch> branch with MR changes
                    batch_mr_sha = self._repo.merge(
                        BatchMergeJob.BATCH_BRANCH_NAME,
                        merge_request.source_branch,
                        '-m',
                        'Batch merge !%s into %s (!%s)' % (
                            merge_request.iid,
                            merge_request.target_branch,
                            batch_mr.iid
                        ),
                        local=True,
                    )
                else:
                    # Update <source_branch> on latest <batch> branch so it contains previous MRs
                    self.fuse(
                        merge_request.source_branch,
                        BatchMergeJob.BATCH_BRANCH_NAME,
                        source_repo_url=source_repo_url,
                        local=True,
                    )
                    # Update <batch> branch with MR changes
                    batch_mr_sha = self._repo.fast_forward(
                        BatchMergeJob.BATCH_BRANCH_NAME,
                        merge_request.source_branch,
                        local=True,
                    )

                # We don't need <source_branch> anymore. Remove it now in case another
                # merge request is using the same branch name in a different project.
                self._repo.remove_branch(merge_request.source_branch)
            except (git.GitError, CannotMerge):
                log.warning('Skipping MR !%s, got conflicts while rebasing', merge_request.iid)
                continue
            else:
                if self._options.use_merge_commit_batches:
                    # update merge_request with the current sha, we will compare it with
                    # the actual sha later to make sure no one pushed this MR meanwhile
                    merge_request.update_sha(actual_sha)

                working_merge_requests.append(merge_request)

        if len(working_merge_requests) <= 1:
            raise CannotBatch('not enough ready merge requests')

        # This switches git to <batch> branch
        self.push_batch()
        for merge_request in working_merge_requests:
            merge_request.comment('I will attempt to batch this MR (!{})...'.format(batch_mr.iid))

        # delay in case Gitlab is slow to respond
        waiting_time_in_secs = 10
        log.debug('Waiting for %s secs for Gitlab to start CI after push', waiting_time_in_secs)
        time.sleep(waiting_time_in_secs)

        # wait for the CI of the batch MR
        if self._project.only_allow_merge_if_pipeline_succeeds:
            try:
                self.wait_for_ci_to_pass(batch_mr, commit_sha=batch_mr_sha)
            except CannotMerge as err:
                for merge_request in working_merge_requests:
                    merge_request.comment(
                        'Batch MR !{batch_mr_iid} failed: {error} I will retry later...'.format(
                            batch_mr_iid=batch_mr.iid,
                            error=err.reason,
                        ),
                    )
                raise CannotBatch(err.reason) from err

        # check each sub MR, and accept each sub MR if using the normal batch
        for merge_request in working_merge_requests:
            try:
                # FIXME: this should probably be part of the merge request
                _, source_repo_url, merge_request_remote = self.fetch_source_project(merge_request)
                self.ensure_mr_not_changed(merge_request)
                # we know the batch MR's CI passed, so we skip CI for sub MRs this time
                self.ensure_mergeable_mr(merge_request, skip_ci=True)

                if not self._options.use_merge_commit_batches:
                    # accept each MRs
                    remote_target_branch_sha = self.accept_mr(
                        merge_request,
                        remote_target_branch_sha,
                        source_repo_url=source_repo_url,
                    )
            except CannotBatch as err:
                merge_request.comment(
                    "I couldn't merge this branch: {error} I will retry later...".format(
                        error=str(err),
                    ),
                )
                raise
            except SkipMerge:
                # Raise here to avoid being caught below - we don't want to be unassigned.
                raise
            except CannotMerge as err:
                self.unassign_from_mr(merge_request)
                merge_request.comment("I couldn't merge this branch: %s" % err.reason)
                raise

        # Accept the batch MR
        if self._options.use_merge_commit_batches:
            # Approve the batch MR using the last sub MR's approvers
            if not batch_mr.fetch_approvals().sufficient:
                approvals = working_merge_requests[-1].fetch_approvals()
                try:
                    approvals.approve(batch_mr)
                except (gitlab.Forbidden, gitlab.Unauthorized):
                    log.exception('Failed to approve MR:')

            try:
                ret = batch_mr.accept(
                    remove_branch=batch_mr.force_remove_source_branch,
                    sha=batch_mr_sha,
                    merge_when_pipeline_succeeds=bool(self._project.only_allow_merge_if_pipeline_succeeds),
                )
                log.info('batch_mr.accept result: %s', ret)
            except gitlab.ApiError as err:
                log.exception('Gitlab API Error:')
                raise CannotMerge('Gitlab API Error: %s' % err) from err
