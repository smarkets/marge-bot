# pylint: disable=protected-access
from unittest.mock import ANY, patch, create_autospec

import pytest

import marge.git
import marge.project
import marge.user
from marge.batch_job import BatchMergeJob, CannotBatch
from marge.gitlab import GET
from marge.job import CannotMerge, MergeJobOptions
from marge.merge_request import MergeRequest
from tests.gitlab_api_mock import MockLab, Ok, commit


class TestBatchJob:
    @pytest.fixture(params=[True, False])
    def fork(self, request):
        return request.param

    @pytest.fixture()
    def mocklab(self, fork):
        return MockLab(fork=fork)

    @pytest.fixture()
    def api(self, mocklab):
        return mocklab.api

    def _mock_merge_request(self, **options):
        return create_autospec(marge.merge_request.MergeRequest, spec_set=True, **options)

    def get_batch_merge_job(self, api, mocklab, **batch_merge_kwargs):
        project_id = mocklab.project_info['id']
        merge_request_iid = mocklab.merge_request_info['iid']

        merge_request = MergeRequest.fetch_by_iid(project_id, merge_request_iid, api)

        params = {
            'api': api,
            'user': marge.user.User.myself(api),
            'project': marge.project.Project.fetch_by_id(project_id, api),
            'repo': create_autospec(marge.git.Repo, spec_set=True),
            'options': MergeJobOptions.default(),
            'merge_requests': [merge_request]
        }
        params.update(batch_merge_kwargs)
        return BatchMergeJob(**params)

    def test_remove_batch_branch(self, api, mocklab):
        repo = create_autospec(marge.git.Repo, spec_set=True)
        batch_merge_job = self.get_batch_merge_job(api, mocklab, repo=repo)
        batch_merge_job.remove_batch_branch()
        repo.remove_branch.assert_called_once_with(
            BatchMergeJob.BATCH_BRANCH_NAME,
        )

    def test_close_batch_mr(self, api, mocklab):
        with patch('marge.batch_job.MergeRequest') as mr_class:
            batch_mr = self._mock_merge_request()
            mr_class.search.return_value = [batch_mr]

            batch_merge_job = self.get_batch_merge_job(api, mocklab)
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

    def test_create_batch_mr(self, api, mocklab):
        with patch('marge.batch_job.MergeRequest') as mr_class:
            batch_mr = self._mock_merge_request()
            mr_class.create.return_value = batch_mr

            batch_merge_job = self.get_batch_merge_job(api, mocklab)
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

    def test_get_mrs_with_common_target_branch(self, api, mocklab):
        master_mrs = [
            self._mock_merge_request(target_branch='master'),
            self._mock_merge_request(target_branch='master'),
        ]
        non_master_mrs = [
            self._mock_merge_request(target_branch='non_master'),
            self._mock_merge_request(target_branch='non_master'),
        ]
        batch_merge_job = self.get_batch_merge_job(
            api, mocklab,
            merge_requests=non_master_mrs + master_mrs,
        )
        r_maser_mrs = batch_merge_job.get_mrs_with_common_target_branch('master')
        assert r_maser_mrs == master_mrs

    @patch.object(BatchMergeJob, 'get_mr_ci_status')
    def test_ensure_mergeable_mr_ci_not_ok(self, bmj_get_mr_ci_status, api, mocklab):
        batch_merge_job = self.get_batch_merge_job(api, mocklab)
        bmj_get_mr_ci_status.return_value = 'failed'
        merge_request = self._mock_merge_request(
            assignee_ids=[batch_merge_job._user.id],
            state='opened',
            work_in_progress=False,
            squash=False,
        )
        merge_request.fetch_approvals.return_value.sufficient = True
        with pytest.raises(CannotBatch) as exc_info:
            batch_merge_job.ensure_mergeable_mr(merge_request)

        assert str(exc_info.value) == 'This MR has not passed CI.'

    def test_push_batch(self, api, mocklab):
        batch_merge_job = self.get_batch_merge_job(api, mocklab)
        batch_merge_job.push_batch()
        batch_merge_job._repo.push.assert_called_once_with(
            BatchMergeJob.BATCH_BRANCH_NAME,
            force=True,
        )

    def test_merge_batch(self, api, mocklab):
        batch_merge_job = self.get_batch_merge_job(api, mocklab)
        target_branch = 'master'
        source_branch = mocklab.merge_request_info['source_branch']
        batch_merge_job.merge_batch(target_branch, source_branch, no_ff=False)
        batch_merge_job._repo.fast_forward.assert_called_once_with(
            target_branch,
            source_branch,
        )

    def test_merge_batch_with_no_ff_enabled(self, api, mocklab):
        batch_merge_job = self.get_batch_merge_job(api, mocklab)
        target_branch = 'master'
        source_branch = mocklab.merge_request_info['source_branch']
        batch_merge_job.merge_batch(target_branch, source_branch, no_ff=True)
        batch_merge_job._repo.merge.assert_called_once_with(
            target_branch,
            source_branch,
            '--no-ff'
        )
        batch_merge_job._repo.fast_forward.assert_not_called()

    def test_ensure_mr_not_changed(self, api, mocklab):
        with patch('marge.batch_job.MergeRequest') as mr_class:
            batch_merge_job = self.get_batch_merge_job(api, mocklab)
            merge_request = self._mock_merge_request()
            changed_merge_request = self._mock_merge_request()
            mr_class.fetch_by_iid.return_value = changed_merge_request

            with pytest.raises(CannotMerge):
                batch_merge_job.ensure_mr_not_changed(merge_request)

            mr_class.fetch_by_iid.assert_called_once_with(
                merge_request.project_id,
                merge_request.iid,
                batch_merge_job._api,
            )

    def test_fuse_mr_when_target_branch_was_moved(self, api, mocklab):
        batch_merge_job = self.get_batch_merge_job(api, mocklab)
        merge_request = self._mock_merge_request(target_branch='master')
        with pytest.raises(CannotBatch) as exc_info:
            batch_merge_job.accept_mr(merge_request, 'abc')
        assert str(exc_info.value) == 'Someone was naughty and by-passed marge'

    def test_fuse_mr_when_source_branch_was_moved(self, api, mocklab):
        batch_merge_job = self.get_batch_merge_job(api, mocklab)
        merge_request = self._mock_merge_request(
            source_project_id=mocklab.merge_request_info['source_project_id'],
            target_branch='master',
            source_branch=mocklab.merge_request_info['source_branch'],
        )

        api.add_transition(
            GET(
                '/projects/{project_iid}/repository/branches/useless_new_feature'.format(
                    project_iid=mocklab.merge_request_info['source_project_id'],
                ),
            ),
            Ok({'commit': commit(commit_id='abc', status='running')}),
        )

        with pytest.raises(CannotMerge) as exc_info:
            batch_merge_job.accept_mr(merge_request, mocklab.initial_master_sha)

        assert str(exc_info.value) == 'Someone pushed to branch while we were trying to merge'
