# pylint: disable=protected-access
from datetime import timedelta
import re
from unittest.mock import ANY, Mock, patch, create_autospec

import pytest

from marge.job import CannotMerge, Fusion, MergeJob, MergeJobOptions, SkipMerge
import marge.interval
import marge.git
import marge.gitlab
import marge.merge_request
import marge.project
import marge.user


class TestJob:
    def _mock_merge_request(self, **options):
        return create_autospec(marge.merge_request.MergeRequest, spec_set=True, **options)

    def get_merge_job(self, **merge_kwargs):
        params = {
            'api': create_autospec(marge.gitlab.Api, spec_set=True),
            'user': create_autospec(marge.user.User, spec_set=True),
            'project': create_autospec(marge.project.Project, spec_set=True),
            'repo': create_autospec(marge.git.Repo, spec_set=True),
            'options': MergeJobOptions.default(),
        }
        params.update(merge_kwargs)
        return MergeJob(**params)

    def test_get_source_project_when_is_target_project(self):
        merge_job = self.get_merge_job()
        merge_request = self._mock_merge_request()
        merge_request.source_project_id = merge_job._project.id
        r_source_project = merge_job.get_source_project(merge_request)
        assert r_source_project is merge_job._project

    def test_get_source_project_when_is_fork(self):
        with patch('marge.job.Project') as project_class:
            merge_job = self.get_merge_job()
            merge_request = self._mock_merge_request()
            r_source_project = merge_job.get_source_project(merge_request)

            project_class.fetch_by_id.assert_called_once_with(
                merge_request.source_project_id,
                api=merge_job._api,
            )
            assert r_source_project is not merge_job._project
            assert r_source_project is project_class.fetch_by_id.return_value

    @pytest.mark.parametrize(
        'version,use_merge_request_pipelines',
        [('9.4.0-ee', False), ('10.5.0-ee', True)],
    )
    def test_get_mr_ci_status(self, version, use_merge_request_pipelines):
        with patch('marge.job.Pipeline', autospec=True) as pipeline_class:
            pipeline_success = [
                Mock(spec=pipeline_class, sha='abc', status='success'),
            ]
            pipeline_class.pipelines_by_branch.return_value = pipeline_success
            pipeline_class.pipelines_by_merge_request.return_value = pipeline_success
            merge_job = self.get_merge_job()
            merge_job._api.version.return_value = marge.gitlab.Version.parse(version)
            merge_request = self._mock_merge_request(sha='abc')

            r_ci_status = merge_job.get_mr_ci_status(merge_request)

            if use_merge_request_pipelines:
                pipeline_class.pipelines_by_merge_request.assert_called_once_with(
                    merge_request.target_project_id,
                    merge_request.iid,
                    merge_job._api,
                )
            else:
                pipeline_class.pipelines_by_branch.assert_called_once_with(
                    merge_request.source_project_id,
                    merge_request.source_branch,
                    merge_job._api,
                )
            assert r_ci_status == 'success'

    def test_ensure_mergeable_mr_not_assigned(self):
        merge_job = self.get_merge_job()
        merge_request = self._mock_merge_request(
            state='opened',
            work_in_progress=False,
            squash=False,
        )
        with pytest.raises(SkipMerge) as exc_info:
            merge_job.ensure_mergeable_mr(merge_request)
        assert exc_info.value.reason == 'It is not assigned to me anymore!'

    def test_ensure_mergeable_mr_state_not_ok(self):
        merge_job = self.get_merge_job()
        merge_request = self._mock_merge_request(
            assignee_ids=[merge_job._user.id],
            state='merged',
            work_in_progress=False,
            squash=False,
        )
        with pytest.raises(CannotMerge) as exc_info:
            merge_job.ensure_mergeable_mr(merge_request)
        assert exc_info.value.reason == 'The merge request is already merged!'

    def test_ensure_mergeable_mr_not_approved(self):
        merge_job = self.get_merge_job()
        merge_request = self._mock_merge_request(
            assignee_ids=[merge_job._user.id],
            state='opened',
            work_in_progress=False,
            squash=False,
        )
        merge_request.fetch_approvals.return_value.sufficient = False
        with pytest.raises(CannotMerge) as exc_info:
            merge_job.ensure_mergeable_mr(merge_request)

        merge_request.fetch_approvals.assert_called_once()
        assert 'Insufficient approvals' in str(exc_info.value)

    def test_ensure_mergeable_mr_wip(self):
        merge_job = self.get_merge_job()
        merge_request = self._mock_merge_request(
            assignee_ids=[merge_job._user.id],
            state='opened',
            work_in_progress=True,
        )
        merge_request.fetch_approvals.return_value.sufficient = True
        with pytest.raises(CannotMerge) as exc_info:
            merge_job.ensure_mergeable_mr(merge_request)

        assert exc_info.value.reason == "Sorry, I can't merge requests marked as Work-In-Progress!"

    def test_ensure_mergeable_mr_unresolved_discussion(self):
        merge_job = self.get_merge_job()
        merge_request = self._mock_merge_request(
            assignee_ids=[merge_job._user.id],
            state='opened',
            work_in_progress=False,
            blocking_discussions_resolved=False,
        )
        merge_request.fetch_approvals.return_value.sufficient = True
        with pytest.raises(CannotMerge) as exc_info:
            merge_job.ensure_mergeable_mr(merge_request)

        assert exc_info.value.reason == "Sorry, I can't merge requests which have unresolved discussions!"

    def test_ensure_mergeable_mr_squash_and_trailers(self):
        merge_job = self.get_merge_job(options=MergeJobOptions.default(add_reviewers=True))
        merge_request = self._mock_merge_request(
            assignee_ids=[merge_job._user.id],
            state='opened',
            work_in_progress=False,
            squash=True,
        )
        merge_request.fetch_approvals.return_value.sufficient = True
        with pytest.raises(CannotMerge) as exc_info:
            merge_job.ensure_mergeable_mr(merge_request)

        assert (
            exc_info.value.reason == "Sorry, merging requests marked as auto-squash "
                                     "would ruin my commit tagging!"
        )

    def test_ensure_mergeable_commit_messages(self):
        merge_job = self.get_merge_job(
            options=MergeJobOptions.default(
                forbid_commit_message=[re.compile("fixup!.*")]
            )
        )
        merge_request = self._mock_merge_request(
            assignee_ids=[merge_job._user.id],
            state="opened",
            work_in_progress=False,
        )
        merge_request.fetch_approvals.return_value.sufficient = True

        commit1 = {"title": "Sanitize for network graph"}
        commit2 = {"title": "fixup! Sanitize for network graph"}
        merge_request.fetch_commits.return_value = [commit1, commit2]

        with pytest.raises(CannotMerge) as exc_info:
            merge_job.ensure_mergeable_mr(merge_request)

        assert (
            exc_info.value.reason
            == "Sorry, I can't merge requests with forbidden commit titles: "
            + "'fixup! Sanitize for network graph' (pattern /fixup!.*/)"
        )

    def test_unassign_from_mr(self):
        merge_job = self.get_merge_job()
        merge_request = self._mock_merge_request()

        # when we are not the author
        merge_job.unassign_from_mr(merge_request)
        merge_request.assign_to.assert_called_once_with(merge_request.author_id)

        # when we are the author
        merge_request.author_id = merge_job._user.id
        merge_job.unassign_from_mr(merge_request)
        merge_request.unassign.assert_called_once()

    def test_fuse_using_rebase(self):
        merge_job = self.get_merge_job(options=MergeJobOptions.default(fusion=Fusion.rebase))
        branch_a = 'A'
        branch_b = 'B'

        merge_job.fuse(branch_a, branch_b)

        merge_job._repo.rebase.assert_called_once_with(
            branch_a,
            branch_b,
            source_repo_url=ANY,
            local=ANY,
        )

    def test_fuse_using_merge(self):
        merge_job = self.get_merge_job(options=MergeJobOptions.default(fusion=Fusion.merge))
        branch_a = 'A'
        branch_b = 'B'

        merge_job.fuse(branch_a, branch_b)

        merge_job._repo.merge.assert_called_once_with(
            branch_a,
            branch_b,
            source_repo_url=ANY,
            local=ANY,
        )


class TestMergeJobOptions:
    def test_default(self):
        assert MergeJobOptions.default() == MergeJobOptions(
            add_tested=False,
            add_part_of=False,
            add_reviewers=False,
            reapprove=False,
            approval_timeout=timedelta(seconds=0),
            embargo=marge.interval.IntervalUnion.empty(),
            ci_timeout=timedelta(minutes=15),
            fusion=Fusion.rebase,
            use_no_ff_batches=False,
            use_merge_commit_batches=False,
            skip_ci_batches=False,
            forbid_commit_message=[]
        )

    def test_default_ci_time(self):
        three_min = timedelta(minutes=3)
        assert MergeJobOptions.default(ci_timeout=three_min) == MergeJobOptions.default()._replace(
            ci_timeout=three_min
        )
