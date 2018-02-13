import logging as log
import time
from datetime import datetime, timedelta

from . import git
from .commit import Commit
from .merge_request import MergeRequest
from .project import Project
from .user import User


class BatchMergeJobError(Exception):
    pass


class MergeableError(BatchMergeJobError):
    pass


class MRChanged(BatchMergeJobError):
    pass


class CIError(BatchMergeJobError):
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

    def delete_batch_mr(self):
        params = {
            'author_id': self._user.id,
            'labels': 'marge_bot_batch',
            'state': 'opened',
            'order_by': 'created_at',
            'sort': 'desc',
        }
        batch_mrs = MergeRequest.search(
            api=self._api,
            project_id=self._project.id,
            params=params,
        ) or []
        for batch_mr in batch_mrs:
            batch_mr.delete()

    def create_batch_mr(self, target_branch):
        params = {
            'source_branch': BatchMergeJob.BATCH_BRANCH_NAME,
            'target_branch': target_branch,
            'title': 'Marge Bot Batch MR - DO NOT TOUCH',
            'labels': 'marge_bot_batch',
        }
        batch_mr = MergeRequest.create(
            api=self._api,
            project_id=self._project.id,
            params=params,
        )
        return batch_mr

    def during_merge_embargo(self):
        now = datetime.utcnow()
        return self._options.embargo.covers(now)

    def unassign_from_merge_request(self, merge_request):
        if merge_request.author_id != self._user.id:
            merge_request.assign_to(merge_request.author_id)
        else:
            merge_request.unassign()

    def get_source_project(self, merge_request):
        source_project = self._project.id
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

    def remove_batch_branch(self):
        try:
            self._repo.remove_branch(BatchMergeJob.BATCH_BRANCH_NAME)
        except git.GitError:
            log.debug('Batch branch does not exist %s', BatchMergeJob.BATCH_BRANCH_NAME)

    def create_batch_branch(self, target_branch):
        self._repo.create_branch(
            BatchMergeJob.BATCH_BRANCH_NAME,
            'origin/%s' % target_branch,
        )

    def get_mrs_with_common_target_branch(self, target_branch):
        return [
            merge_request for merge_request in self._merge_requests
            if merge_request.target_branch == target_branch
        ]

    def ensure_mergeable_mr(self, merge_request):
        merge_request.refetch_info()
        if self._user.id != merge_request.assignee_id:
            raise MergeableError(
                'It is not assigned to us anymore! -- SKIPPING',
            )
        state = merge_request.state
        if state not in ('opened', 'reopened', 'locked'):
            if state in ('merged', 'closed'):
                raise MergeableError(
                    'The merge request is already %s!' % state,
                )
            raise MergeableError(
                'The merge request is in an unknown state: %s' % state,
            )
        approvals = merge_request.fetch_approvals()
        if not approvals.sufficient:
            message = ''.join([
                'Insufficient approvals ',
                '(have: {0.approver_usernames} missing: {0.approvals_left})'.format(approvals)
            ])
            raise MergeableError(message)
        if merge_request.work_in_progress:
            raise MergeableError(
                "Sorry, I can't merge requests marked as Work-In-Progress!",
            )
        if merge_request.squash and self._options.requests_commit_tagging:
            raise MergeableError(
                'Sorry, merging requests marked as auto-squash would ruin my commit tagging!',
            )
        # FIXME: is this correct?
        # Should we still consider MRs from source_projects that don't have CI?
        if self._project.only_allow_merge_if_pipeline_succeeds:
            ci_status = self.get_mr_ci_status(merge_request)
            if ci_status != 'success':
                raise MergeableError('CI status is %s' % ci_status)

    def get_meargeable_mrs(self, merge_requests):
        meargeable_mrs = []
        for merge_request in merge_requests:
            try:
                self.ensure_mergeable_mr(merge_request)
            except MergeableError as ex:
                log.warning(ex)
                continue
            else:
                meargeable_mrs.append(merge_request)
        return meargeable_mrs

    def fetch_mr(self, merge_request):
        # This method expects MR's source project to be different from target project
        source_project = self.get_source_project(merge_request)
        assert source_project is not self._project
        self._repo.fetch(
            remote='source',
            remote_url=source_project.ssh_url_to_repo,
        )

    def fuse_branch_a_on_branch_b(self, branch_a, branch_b):
        strategy = 'merge' if self._options.use_merge_strategy else 'rebase'
        return self._repo.fuse(
            strategy,
            branch_a,
            branch_b,
        )

    def push_batch(self):
        self._repo.push_force(BatchMergeJob.BATCH_BRANCH_NAME)

    def wait_for_ci_to_pass(self, merge_request):
        time_0 = datetime.utcnow()
        waiting_time_in_secs = 10

        log.info('Waiting for CI to pass')
        while datetime.utcnow() - time_0 < self._options.ci_timeout:
            ci_status = self.get_mr_ci_status(merge_request)
            if ci_status == 'success':
                return
            if ci_status in ['failed', 'canceled']:
                raise CIError('CI %s' % ci_status)
            if ci_status not in ('pending', 'running'):
                log.warning('Suspicious CI status: %r', ci_status)
            log.debug('Waiting for %s secs before polling CI status again', waiting_time_in_secs)
            time.sleep(waiting_time_in_secs)
        raise CIError('CI is taking too long')

    def ensure_mr_not_changed(self, merge_request):
        updated_mr = MergeRequest.fetch_by_iid(
            merge_request.project_id,
            merge_request.iid,
            self._api,
        )
        if updated_mr.source_branch != merge_request.source_branch:
            raise MRChanged('MR Changed: source branch')
        if updated_mr.source_project_id != merge_request.source_project_id:
            raise MRChanged('MR Changed: source project id')

        if updated_mr.target_branch != merge_request.target_branch:
            raise MRChanged('MR Changed: target branch')
        if updated_mr.target_project_id != merge_request.target_project_id:
            raise MRChanged('MR Changed: target project id')

        if updated_mr.sha != merge_request.sha:
            raise MRChanged('MR Changed: SHA')

    def add_trailers(self, merge_request, mr_local_branch):

        def _get_reviewer_names_and_emails():
            approvals = merge_request.fetch_approvals()
            uids = approvals.approver_ids
            return ['{0.name} <{0.email}>'.format(User.fetch_by_id(uid, self._api)) for uid in uids]

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
                branch=mr_local_branch,
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
                branch=mr_local_branch,
                start_commit=mr_local_branch + '^'
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
                branch=mr_local_branch,
                start_commit='origin/' + merge_request.target_branch,
            )
        return sha

    def fuse_mr(self, merge_request):
        origin_target_branch = 'origin/%s' % merge_request.target_branch
        current_target_sha = self._repo.get_commit_hash(origin_target_branch)
        self._repo.fetch('origin')
        moved_target_sha = self._repo.get_commit_hash(origin_target_branch)
        assert current_target_sha == moved_target_sha

        merge_request_remote = 'origin'
        if merge_request.source_project_id != self._project.id:
            self.fetch_mr(merge_request)
            merge_request_remote = 'source'
        mr_local_branch = merge_request.source_branch
        self._repo.create_branch(
            mr_local_branch,
            '%s/%s' % (merge_request_remote, merge_request.source_branch),
        )
        sha = self.fuse_branch_a_on_branch_b(
            mr_local_branch,
            'origin/%s' % merge_request.target_branch,
        )
        sha = self.add_trailers(merge_request, mr_local_branch) or sha

        source_project = (
            self._project if merge_request.source_project_id == self._project.id else
            Project.fetch_by_id(merge_request.source_project_id, api=self._api)
        )
        source_repo_url = None if source_project is self._project else source_project.ssh_url_to_repo
        self._repo.push_force(merge_request.source_branch, source_repo_url)
        self._repo.checkout_branch(
            merge_request.target_branch,
            'origin/%s' % merge_request.target_branch,
        )
        sha = self.fuse_branch_a_on_branch_b(
            merge_request.target_branch,
            mr_local_branch,
        )
        self._repo.push(merge_request.target_branch)

    def wait_for_branch_to_be_merged(self, merge_request):
        time_0 = datetime.utcnow()
        waiting_time_in_secs = 10

        while datetime.utcnow() - time_0 < timedelta(minutes=5):
            merge_request.refetch_info()

            if merge_request.state == 'merged':
                return  # success!
            if merge_request.state == 'closed':
                raise MergeableError('someone closed the merge request while merging!')
            assert merge_request.state in ('opened', 'reopened', 'locked'), merge_request.state

            log.info('Giving %s more secs for !%s to be merged...', waiting_time_in_secs, merge_request.iid)
            time.sleep(waiting_time_in_secs)

        raise MergeableError('It is taking too long to see the request marked as merged!')

    def execute(self):
        if self.during_merge_embargo():
            log.info('Merge embargo! -- SKIPPING')
            return
        self.remove_batch_branch()
        self.delete_batch_mr()
        self._repo.fetch('origin')
        # self._merge_requests is sorted by oldest first.
        # take it's target branch and batch all MRs with that target branch
        target_branch = self._merge_requests[0].target_branch
        self._repo.checkout_branch(target_branch, 'origin/%s' % target_branch)
        self.create_batch_branch(target_branch)
        merge_requests = self.get_mrs_with_common_target_branch(target_branch)
        merge_requests = self.get_meargeable_mrs(merge_requests)
        for merge_request in merge_requests:
            merge_request_remote = 'origin'
            if merge_request.source_project_id != self._project.id:
                self.fetch_mr(merge_request)
                merge_request_remote = 'source'
            mr_local_branch = merge_request.source_branch
            self._repo.create_branch(
                mr_local_branch,
                '%s/%s' % (merge_request_remote, merge_request.source_branch),
            )
            # update local MR branch on latest batch branch so it contains previous MRs in the batch
            # this will catch conflicts
            self.fuse_branch_a_on_branch_b(
                branch_a=mr_local_branch,
                branch_b=BatchMergeJob.BATCH_BRANCH_NAME,
            )
            # update batch branch with MR changes
            # This only make sense if we want run CI on batch
            if self._project.only_allow_merge_if_pipeline_succeeds:
                self.fuse_branch_a_on_branch_b(
                    branch_a=BatchMergeJob.BATCH_BRANCH_NAME,
                    branch_b=mr_local_branch,
                )
            self._repo.remove_branch(mr_local_branch)
        if self._project.only_allow_merge_if_pipeline_succeeds:
            self.push_batch()
            batch_mr = self.create_batch_mr(
                target_branch=target_branch,
            )
            self.wait_for_ci_to_pass(batch_mr)
        for merge_request in merge_requests:
            try:
                self.ensure_mr_not_changed(merge_request)
                self.ensure_mergeable_mr(merge_request)
                self.fuse_mr(merge_request)
            except (MRChanged, MergeableError) as ex:
                log.warning(ex)
                merge_request.comment(str(ex))
                self.unassign_from_merge_request(merge_request)
                raise
