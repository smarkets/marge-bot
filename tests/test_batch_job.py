# pylint: disable=protected-access
from unittest.mock import ANY, Mock, patch

import pytest

import marge.git
import marge.project
import marge.user
from marge.batch_job import BatchMergeJob, CannotBatch
from marge.gitlab import GET
from marge.job import CannotMerge, MergeJobOptions
from marge.merge_request import MergeRequest
from tests.gitlab_api_mock import MockLab, Ok, commit


# pylint: disable=attribute-defined-outside-init
class TestBatchJob(object):
    def setup_method(self, _method):
        self.mocklab = MockLab()
        self.api = self.mocklab.api

    def get_batch_merge_job(self, **batch_merge_kwargs):
        api, mocklab = self.api, self.mocklab

        project_id = mocklab.project_info['id']
        merge_request_iid = mocklab.merge_request_info['iid']

        merge_request = MergeRequest.fetch_by_iid(project_id, merge_request_iid, api)

        params = {
            'api': api,
            'user': marge.user.User.myself(self.api),
            'project': marge.project.Project.fetch_by_id(project_id, api),
            'repo': Mock(marge.git.Repo),
            'options': MergeJobOptions.default(),
            'merge_requests': [merge_request]
        }
        params.update(batch_merge_kwargs)
        return BatchMergeJob(**params)

    def test_remove_batch_branch(self):
        repo = Mock()
        batch_merge_job = self.get_batch_merge_job(repo=repo)
        batch_merge_job.remove_batch_branch()
        repo.remove_branch.assert_called_once_with(
            BatchMergeJob.BATCH_BRANCH_NAME,
        )

    def test_close_batch_mr(self):
        with patch('marge.batch_job.MergeRequest') as mr_class:
            batch_mr = Mock()
            mr_class.search.return_value = [batch_mr]

            batch_merge_job = self.get_batch_merge_job()
            batch_merge_job.close_batch_mr()

            params = {
                'author_id': batch_merge_job._user.id,
                'labels': BatchMergeJob.BATCH_BRANCH_NAME,
                'state': 'opened',
                'order_by': 'created_at',
                'sort': 'desc',
            }
            mr_class.search.assert_called_once_with(
                api=ANY,
                project_id=ANY,
                params=params,
            )
            batch_mr.close.assert_called_once()

    def test_create_batch_mr(self):
        with patch('marge.batch_job.MergeRequest') as mr_class:
            batch_mr = Mock()
            mr_class.create.return_value = batch_mr

            batch_merge_job = self.get_batch_merge_job()
            target_branch = 'master'
            r_batch_mr = batch_merge_job.create_batch_mr(target_branch)

            params = {
                'source_branch': BatchMergeJob.BATCH_BRANCH_NAME,
                'target_branch': target_branch,
                'title': 'Marge Bot Batch MR - DO NOT TOUCH',
                'labels': BatchMergeJob.BATCH_BRANCH_NAME,
            }
            mr_class.create.assert_called_once_with(
                api=ANY,
                project_id=ANY,
                params=params,
            )
            assert r_batch_mr is batch_mr

    def test_get_mrs_with_common_target_branch(self):
        master_mrs = [
            Mock(target_branch='master'),
            Mock(target_branch='master'),
        ]
        non_master_mrs = [
            Mock(target_branch='non_master'),
            Mock(target_branch='non_master'),
        ]
        batch_merge_job = self.get_batch_merge_job(
            merge_requests=non_master_mrs + master_mrs,
        )
        r_maser_mrs = batch_merge_job.get_mrs_with_common_target_branch('master')
        assert r_maser_mrs == master_mrs

    @patch.object(BatchMergeJob, 'get_mr_ci_status')
    def test_ensure_mergeable_mr_ci_not_ok(self, bmj_get_mr_ci_status):
        batch_merge_job = self.get_batch_merge_job()
        bmj_get_mr_ci_status.return_value = 'failed'
        merge_request = Mock(
            assignee_id=batch_merge_job._user.id,
            state='opened',
            work_in_progress=False,
            squash=False,
        )
        merge_request.fetch_approvals.return_value.sufficient = True
        with pytest.raises(CannotBatch) as exc_info:
            batch_merge_job.ensure_mergeable_mr(merge_request)

        assert str(exc_info.value) == 'This MR has not passed CI.'

    def test_push_batch(self):
        batch_merge_job = self.get_batch_merge_job()
        batch_merge_job.push_batch()
        batch_merge_job._repo.push.assert_called_once_with(
            BatchMergeJob.BATCH_BRANCH_NAME,
            force=True,
        )

    def test_ensure_mr_not_changed(self):
        with patch('marge.batch_job.MergeRequest') as mr_class:
            batch_merge_job = self.get_batch_merge_job()
            merge_request = Mock()
            changed_merge_request = Mock()
            mr_class.fetch_by_iid.return_value = changed_merge_request

            with pytest.raises(CannotMerge):
                batch_merge_job.ensure_mr_not_changed(merge_request)

            mr_class.fetch_by_iid.assert_called_once_with(
                merge_request.project_id,
                merge_request.iid,
                batch_merge_job._api,
            )

    def test_fuse_mr_when_target_branch_was_moved(self):
        batch_merge_job = self.get_batch_merge_job()
        merge_request = Mock(target_branch='master')
        with pytest.raises(CannotBatch) as exc_info:
            batch_merge_job.accept_mr(merge_request, 'abc')
        assert str(exc_info.value) == 'Someone was naughty and by-passed marge'

    def test_fuse_mr_when_source_branch_was_moved(self):
        api, mocklab = self.api, self.mocklab
        batch_merge_job = self.get_batch_merge_job()
        merge_request = Mock(
            source_project_id=batch_merge_job._project.id,
            target_branch='master',
            source_branch=self.mocklab.merge_request_info['source_branch'],
        )

        api.add_transition(
            GET('/projects/1234/repository/branches/useless_new_feature'),
            Ok({'commit': commit(commit_id='abc', status='running')}),
        )

        with pytest.raises(CannotMerge) as exc_info:
            batch_merge_job.accept_mr(merge_request, mocklab.initial_master_sha)

        assert str(exc_info.value) == 'Someone pushed to branch while we were trying to merge'
