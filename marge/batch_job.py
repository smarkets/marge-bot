import logging as log
import time
from datetime import datetime

from . import git
from .commit import Commit
from .merge_request import MergeRequest
from .project import Project
from .user import User


MERGE_ERROR_MSG = {
    'NOT_ASSIGNED': 'Not assigned to me.',
    'NOT_APPROVED': 'Not fully approved.',
    'WIP': 'Is marked as Work-In-Progress.',
    'STATE_NOT_OK': 'Is in %s state.',
    'SQUASH_AND_TRAILERS': 'Is marked as auto-squash but trailers are enabled.',
    'CI_NOT_OK': 'Has unsuccessful CI status: %s.',
    'CI_TIMEOUT': 'CI is taking too long.',
    'CHANGED': 'The %s has changed.',
}


class MergeError(Exception):

    def __init__(self, *, mr_iid, message_key, message):
        assert message_key in MERGE_ERROR_MSG.keys()
        super().__init__(message)
        self.mr_iid = mr_iid
        self.message_key = message_key

    def log_str(self):
        return 'MR !%s: %s' % (self.mr_iid, self)

    def comment_str(self):
        return 'Sorry, %s' % self


class PreMergeError(Exception):
    pass


class BatchMergeJob:

    BATCH_BRANCH_NAME = 'marge_bot_batch_merge_job'

    def __init__(self, *, api, user, project, merge_requests, repo, options):
        self._api = api
        self._user = user
        self._project = project
        self._merge_requests = merge_requests
        self._repo = repo
        self._options = options

    def remove_batch_branch(self):
        log.info('Removing local batch branch')
        try:
            self._repo.remove_branch(BatchMergeJob.BATCH_BRANCH_NAME)
        except git.GitError:
            pass

    def delete_batch_mr(self):
        log.info('Deleting batch MRs')
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
            log.info('Deleting batch MR !%s', batch_mr.iid)
            batch_mr.delete()

    def create_batch_mr(self, target_branch):
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

    def during_merge_embargo(self):
        now = datetime.utcnow()
        return self._options.embargo.covers(now)

    def unassign_from_mr(self, merge_request):
        log.info('Unassigning from MR !%s', merge_request.iid)
        if merge_request.author_id != self._user.id:
            merge_request.assign_to(merge_request.author_id)
        else:
            merge_request.unassign()

    def get_source_project(self, merge_request):
        source_project = self._project
        if merge_request.source_project_id != self._project.id:
            source_project = Project.fetch_by_id(
                merge_request.source_project_id,
                api=self._api,
            )
        return source_project

    def get_mr_ci_status(self, merge_request):
        return Commit.fetch_by_id(
            merge_request.source_project_id,
            merge_request.sha,
            self._api,
        ).status

    def get_mrs_with_common_target_branch(self, target_branch):
        log.info('Filtering MRs with target branch %s', target_branch)
        return [
            merge_request for merge_request in self._merge_requests
            if merge_request.target_branch == target_branch
        ]

    def ensure_mergeable_mr(self, merge_request):
        merge_request.refetch_info()
        log.info('Ensuring MR !%s is mergeable', merge_request.iid)
        log.debug('Ensuring MR %r is mergeable', merge_request)
        if self._user.id != merge_request.assignee_id:
            msg_key = 'NOT_ASSIGNED'
            raise MergeError(
                mr_iid=merge_request.iid,
                message_key=msg_key,
                message=MERGE_ERROR_MSG[msg_key],
            )
        state = merge_request.state
        if state not in ('opened', 'reopened', 'locked'):
            msg_key = 'STATE_NOT_OK'
            raise MergeError(
                mr_iid=merge_request.iid,
                message_key=msg_key,
                message=MERGE_ERROR_MSG[msg_key] % state,
            )
        approvals = merge_request.fetch_approvals()
        if not approvals.sufficient:
            msg_key = 'NOT_APPROVED'
            raise MergeError(
                mr_iid=merge_request.iid,
                message_key=msg_key,
                message=MERGE_ERROR_MSG[msg_key],
            )
        if merge_request.work_in_progress:
            msg_key = 'WIP'
            raise MergeError(
                mr_iid=merge_request.iid,
                message_key=msg_key,
                message=MERGE_ERROR_MSG[msg_key],
            )
        if merge_request.squash and self._options.requests_commit_tagging:
            msg_key = 'SQUASH_AND_TRAILERS'
            raise MergeError(
                mr_iid=merge_request.iid,
                message_key=msg_key,
                message=MERGE_ERROR_MSG[msg_key],
            )
        # FIXME: is this ok?
        # If the MR comes from a fork
        # and the fork doesn't have CI set up
        # and the target project has 'only_allow_merge_if_pipeline_succeeds'
        # Then MR can't be merged
        if self._project.only_allow_merge_if_pipeline_succeeds:
            ci_status = self.get_mr_ci_status(merge_request)
            if ci_status != 'success':
                msg_key = 'CI_NOT_OK'
                raise MergeError(
                    mr_iid=merge_request.iid,
                    message_key=msg_key,
                    message=MERGE_ERROR_MSG[msg_key] % ci_status,
                )

    def get_mergeable_mrs(self, merge_requests):
        log.info('Filtering mergeable MRs')
        mergeable_mrs = []
        for merge_request in merge_requests:
            try:
                self.ensure_mergeable_mr(merge_request)
            except MergeError as ex:
                log.warning('%s - Skipping it!', ex.log_str())
                continue
            else:
                mergeable_mrs.append(merge_request)
        return mergeable_mrs

    def fetch_mr(self, merge_request):
        # This method expects MR's source project to be different from target project
        source_project = self.get_source_project(merge_request)
        assert source_project is not self._project
        self._repo.fetch(
            remote='source',
            remote_url=source_project.ssh_url_to_repo,
        )

    def fuse_branch_a_on_branch_b(self, branch_a, branch_b):
        # NOTE: this leaves git switched to branch_a

        strategy = 'merge' if self._options.use_merge_strategy else 'rebase'
        log.info('%s %s on %s', strategy, branch_a, branch_b)
        return self._repo.fuse(
            strategy,
            branch_a,
            branch_b,
        )

    def push_batch(self):
        log.info('Pushing batch branch')
        self._repo.push(BatchMergeJob.BATCH_BRANCH_NAME, force=True)

    def wait_for_ci_to_pass(self, merge_request):
        time_0 = datetime.utcnow()
        waiting_time_in_secs = 10

        log.info('Waiting for CI to pass for MR !%s', merge_request.iid)
        while datetime.utcnow() - time_0 < self._options.ci_timeout:
            ci_status = self.get_mr_ci_status(merge_request)
            if ci_status == 'success':
                log.info('CI for MR !%s passed', merge_request.iid)
                return
            if ci_status in ['failed', 'canceled']:
                msg_key = 'CI_NOT_OK'
                raise MergeError(
                    mr_iid=merge_request.iid,
                    message_key=msg_key,
                    message=MERGE_ERROR_MSG[msg_key].format(ci_status),
                )
            if ci_status not in ('pending', 'running'):
                log.warning('Suspicious CI status: %r', ci_status)
            log.debug('Waiting for %s secs before polling CI status again', waiting_time_in_secs)
            time.sleep(waiting_time_in_secs)
        msg_key = 'CI_TIMEOUT'
        raise MergeError(
            mr_iid=merge_request.iid,
            message_key=msg_key,
            message=MERGE_ERROR_MSG[msg_key],
        )

    def ensure_mr_not_changed(self, merge_request):
        log.info('Ensuring MR !%s did not change', merge_request.iid)
        changed_mr = MergeRequest.fetch_by_iid(
            merge_request.project_id,
            merge_request.iid,
            self._api,
        )
        msg_key = 'CHANGED'
        if changed_mr.source_branch != merge_request.source_branch:
            raise MergeError(
                mr_iid=merge_request.iid,
                message_key=msg_key,
                message=MERGE_ERROR_MSG[msg_key] % 'source branch',
            )
        if changed_mr.source_project_id != merge_request.source_project_id:
            raise MergeError(
                mr_iid=merge_request.iid,
                message_key=msg_key,
                message=MERGE_ERROR_MSG[msg_key] % 'source project id',
            )
        if changed_mr.target_branch != merge_request.target_branch:
            raise MergeError(
                mr_iid=merge_request.iid,
                message_key=msg_key,
                message=MERGE_ERROR_MSG[msg_key] % 'target branch',
            )
        if changed_mr.target_project_id != merge_request.target_project_id:
            raise MergeError(
                mr_iid=merge_request.iid,
                message_key=msg_key,
                message=MERGE_ERROR_MSG[msg_key] % 'target project id',
            )
        if changed_mr.sha != merge_request.sha:
            raise MergeError(
                mr_iid=merge_request.iid,
                message_key=msg_key,
                message=MERGE_ERROR_MSG[msg_key] % 'SHA',
            )

    def add_trailers(self, merge_request):

        def _get_reviewer_names_and_emails():
            approvals = merge_request.fetch_approvals()
            uids = approvals.approver_ids
            return ['{0.name} <{0.email}>'.format(User.fetch_by_id(uid, self._api)) for uid in uids]

        log.info('Adding trailers for MR !%s', merge_request.iid)

        # add Reviewed-by
        reviewers = (
            _get_reviewer_names_and_emails() if self._options.add_reviewers
            else None
        )
        sha = None
        if reviewers is not None:
            sha = self._repo.tag_with_trailer(
                trailer_name='Reviewed-by',
                trailer_values=reviewers,
                branch=merge_request.source_branch,
                start_commit='origin/' + merge_request.target_branch,
            )

        # add Tested-by
        should_add_tested = self._options.add_tested and self._project.only_allow_merge_if_pipeline_succeeds
        tested_by = (
            ['{0._user.name} <{1.web_url}>'.format(self, merge_request)] if should_add_tested
            else None
        )
        if tested_by is not None and not self._options.use_merge_strategy:
            sha = self._repo.tag_with_trailer(
                trailer_name='Tested-by',
                trailer_values=tested_by,
                branch=merge_request.source_branch,
                start_commit=merge_request.source_branch + '^'
            )

        # add Part-of
        part_of = (
            '<{0.web_url}>'.format(merge_request) if self._options.add_part_of
            else None
        )
        if part_of is not None:
            sha = self._repo.tag_with_trailer(
                trailer_name='Part-of',
                trailer_values=[part_of],
                branch=merge_request.source_branch,
                start_commit='origin/' + merge_request.target_branch,
            )
        return sha

    def fuse_mr(
        self,
        merge_request,
        expected_remote_target_branch_sha,
    ):
        log.info('Fusing MR !%s', merge_request.iid)
        # Make sure latest commit in remote <target_branch> is the one we tested against
        self._repo.fetch('origin')
        remote_target_branch_sha = self._repo.get_commit_hash(
            'origin/%s' % merge_request.target_branch,
        )
        assert remote_target_branch_sha == expected_remote_target_branch_sha

        # Make sure we have MR commits fetched
        merge_request_remote = 'origin'
        if merge_request.source_project_id != self._project.id:
            self.fetch_mr(merge_request)
            merge_request_remote = 'source'

        # Make sure latest commit in remote <source_branch> is the one we tested against
        remote_source_branch_sha = self._repo.get_commit_hash(
            '%s/%s' % (merge_request_remote, merge_request.source_branch),
        )
        assert remote_source_branch_sha == merge_request.sha

        # This switches git to <source_branch>
        self._repo.checkout_branch(
            merge_request.source_branch,
            '%s/%s' % (merge_request_remote, merge_request.source_branch),
        )
        # This switches git to <source_branch>
        sha = self.fuse_branch_a_on_branch_b(
            merge_request.source_branch,
            'origin/%s' % merge_request.target_branch,
        )
        sha = self.add_trailers(merge_request) or sha

        source_project = self.get_source_project(merge_request)
        source_repo_url = None if source_project is self._project else source_project.ssh_url_to_repo
        # FIXME: Should we re-approve after pushing?
        self._repo.push(
            merge_request.source_branch,
            source_repo_url,
            force=True,
        )
        # This switches git to <target_branch>
        self._repo.checkout_branch(
            merge_request.target_branch,
            'origin/%s' % merge_request.target_branch,
        )
        # This switches git to <target_branch>
        # This should be a fast-forward, no actual rebase/merge should happen,
        # and SHA shouldn't change
        sha = self.fuse_branch_a_on_branch_b(
            merge_request.target_branch,
            merge_request.source_branch,
        )
        self._repo.push(merge_request.target_branch)
        return sha

    def execute(self):
        if self.during_merge_embargo():
            log.info('Merge embargo! -- SKIPPING')
            return
        # Let's make sure we have latest changes
        self._repo.fetch('origin')
        # Let's assume we have no idea where we are in local git now.
        # Switch to master so we have a starting point and
        # reset it to origin/master
        self._repo.checkout_branch('master', 'origin/master')

        # Cleanup previous batch work
        self.remove_batch_branch()
        self.delete_batch_mr()

        # self._merge_requests is sorted by oldest first.
        # take it's target branch and batch all MRs with that target branch
        target_branch = self._merge_requests[0].target_branch
        merge_requests = self.get_mrs_with_common_target_branch(target_branch)
        merge_requests = self.get_mergeable_mrs(merge_requests)
        if not merge_requests:
            # No merge requests are ready to be merged. Let's raise an error
            #  to do a basic job, as the rebase there might fix it.
            raise PreMergeError('All MRs are currently unmergeable!')

        # Save the sha of remote <target_branch> so we can use it to make sure
        # the remote wasn't changed while we're testing against it
        remote_target_branch_sha = self._repo.get_commit_hash(
            'origin/%s' % target_branch,
        )

        # create/reset local <target_branch> based on latest origin/<target_branch>
        # This switches git to <target_branch>.
        self._repo.checkout_branch(
            target_branch,
            'origin/%s' % target_branch,
        )
        # create batch branch based on origin/<target_branch>
        # This switches git to <batch>.
        self._repo.checkout_branch(
            BatchMergeJob.BATCH_BRANCH_NAME,
            'origin/%s' % target_branch,
        )
        for merge_request in merge_requests:
            merge_request_remote = 'origin'
            # Add remote for forked project and fetch it
            if merge_request.source_project_id != self._project.id:
                self.fetch_mr(merge_request)
                merge_request_remote = 'source'
            # Create a local <source_branch> based on MR's remote/<source_branch>
            # This switches git to <source_branch>.
            self._repo.checkout_branch(
                merge_request.source_branch,
                '%s/%s' % (merge_request_remote, merge_request.source_branch),
            )
            # Update <source_branch> on latest <batch> branch so it contains previous MRs
            # this will help us catch conflicts with prev MRs
            # And makes sure we can fuse it in <batch> branch
            # This switches git to <source_branch>
            self.fuse_branch_a_on_branch_b(
                branch_a=merge_request.source_branch,
                branch_b=BatchMergeJob.BATCH_BRANCH_NAME,
            )
            # update <batch> branch with MR changes
            # This switches git back to <batch> branch
            self.fuse_branch_a_on_branch_b(
                branch_a=BatchMergeJob.BATCH_BRANCH_NAME,
                branch_b=merge_request.source_branch,
            )
            # we don't need <source_branch> anymore
            self._repo.remove_branch(merge_request.source_branch)
        if self._project.only_allow_merge_if_pipeline_succeeds:
            # This switches git to <batch> branch
            self.push_batch()
            batch_mr = self.create_batch_mr(
                target_branch=target_branch,
            )
            self.wait_for_ci_to_pass(batch_mr)
        for merge_request in merge_requests:
            try:
                self.ensure_mr_not_changed(merge_request)
                self.ensure_mergeable_mr(merge_request)
                remote_target_branch_sha = self.fuse_mr(
                    merge_request,
                    remote_target_branch_sha,
                )
            except MergeError as ex:
                log.warning(ex.log_str())
                merge_request.comment(ex.comment_str())
                if ex.message_key != 'NOT_ASSIGNED':
                    self.unassign_from_mr(merge_request)
                raise
