# pylint: disable=protected-access
from unittest.mock import ANY, call, Mock, patch

import pytest

from marge.batch_job import BatchMergeJob, MergeError


def get_batch_merge_job(
    api=Mock(),
    user=Mock(),
    project=Mock(),
    merge_requests=Mock(),
    repo=Mock(),
    options=Mock(),
):
    return BatchMergeJob(
        api=api,
        user=user,
        project=project,
        merge_requests=merge_requests,
        repo=repo,
        options=options,
    )


def test_remove_batch_branch():
    repo = Mock()
    batch_merge_job = get_batch_merge_job(repo=repo)
    batch_merge_job.remove_batch_branch()
    repo.remove_branch.assert_called_once_with(
        BatchMergeJob.BATCH_BRANCH_NAME,
    )


def test_delete_batch_mr():
    with patch('marge.batch_job.MergeRequest') as mr_class:
        batch_mr = Mock()
        mr_class.search.return_value = [batch_mr]

        batch_merge_job = get_batch_merge_job()
        batch_merge_job.delete_batch_mr()

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
        batch_mr.delete.assert_called_once()


def test_create_batch_mr():
    with patch('marge.batch_job.MergeRequest') as mr_class:
        batch_mr = Mock()
        mr_class.create.return_value = batch_mr

        batch_merge_job = get_batch_merge_job()
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


def test_unassign_from_mr():
    batch_merge_job = get_batch_merge_job()
    merge_request = Mock()

    # when we are not the author
    batch_merge_job.unassign_from_mr(merge_request)
    merge_request.assign_to.assert_called_once_with(merge_request.author_id)

    # when we are the author
    merge_request.author_id = batch_merge_job._user.id
    batch_merge_job.unassign_from_mr(merge_request)
    merge_request.unassign.assert_called_once()


def test_get_source_project_when_is_target_project():
    batch_merge_job = get_batch_merge_job()
    merge_request = Mock()
    merge_request.source_project_id = batch_merge_job._project.id
    r_source_project = batch_merge_job.get_source_project(merge_request)
    assert r_source_project is batch_merge_job._project


def test_get_source_project_when_is_fork():
    with patch('marge.batch_job.Project') as project_class:
        batch_merge_job = get_batch_merge_job()
        merge_request = Mock()
        r_source_project = batch_merge_job.get_source_project(merge_request)

        project_class.fetch_by_id.assert_called_once_with(
            merge_request.source_project_id,
            api=batch_merge_job._api,
        )
        assert r_source_project is not batch_merge_job._project
        assert r_source_project is project_class.fetch_by_id.return_value


def test_get_mr_ci_status():
    with patch('marge.batch_job.Commit') as commit_class:
        commit_class.fetch_by_id.return_value = Mock(status='success')
        batch_merge_job = get_batch_merge_job()
        merge_request = Mock()

        r_ci_status = batch_merge_job.get_mr_ci_status(merge_request)

        commit_class.fetch_by_id.assert_called_once_with(
            merge_request.source_project_id,
            merge_request.sha,
            batch_merge_job._api,
        )
        assert r_ci_status == 'success'


def test_get_mrs_with_common_target_branch():
    master_mrs = [
        Mock(target_branch='master'),
        Mock(target_branch='master'),
    ]
    non_master_mrs = [
        Mock(target_branch='non_master'),
        Mock(target_branch='non_master'),
    ]
    batch_merge_job = get_batch_merge_job(
        merge_requests=non_master_mrs + master_mrs,
    )
    r_maser_mrs = batch_merge_job.get_mrs_with_common_target_branch('master')
    assert r_maser_mrs == master_mrs


def test_ensure_mergeable_mr_not_assigned():
    batch_merge_job = get_batch_merge_job()
    merge_request = Mock()
    with pytest.raises(MergeError) as exc_info:
        batch_merge_job.ensure_mergeable_mr(merge_request)
    assert exc_info.value.message_key == 'NOT_ASSIGNED'


def test_ensure_mergeable_mr_state_not_ok():
    batch_merge_job = get_batch_merge_job()
    merge_request = Mock(
        assignee_id=batch_merge_job._user.id,
        state='merged',
    )
    with pytest.raises(MergeError) as exc_info:
        batch_merge_job.ensure_mergeable_mr(merge_request)
    assert exc_info.value.message_key == 'STATE_NOT_OK'


def test_ensure_mergeable_mr_not_approved():
    batch_merge_job = get_batch_merge_job()
    merge_request = Mock(
        assignee_id=batch_merge_job._user.id,
        state='opened',
    )
    merge_request.fetch_approvals.return_value.sufficient = False
    with pytest.raises(MergeError) as exc_info:
        batch_merge_job.ensure_mergeable_mr(merge_request)

    merge_request.fetch_approvals.assert_called_once()
    assert exc_info.value.message_key == 'NOT_APPROVED'


def test_ensure_mergeable_mr_wip():
    batch_merge_job = get_batch_merge_job()
    merge_request = Mock(
        assignee_id=batch_merge_job._user.id,
        state='opened',
        work_in_progress=True,
    )
    merge_request.fetch_approvals.return_value.sufficient = True
    with pytest.raises(MergeError) as exc_info:
        batch_merge_job.ensure_mergeable_mr(merge_request)

    assert exc_info.value.message_key == 'WIP'


def test_ensure_mergeable_mr_squash_and_trailers():
    batch_merge_job = get_batch_merge_job()
    batch_merge_job._options.requests_commit_tagging = True
    merge_request = Mock(
        assignee_id=batch_merge_job._user.id,
        state='opened',
        work_in_progress=False,
        squash=True,
    )
    merge_request.fetch_approvals.return_value.sufficient = True
    with pytest.raises(MergeError) as exc_info:
        batch_merge_job.ensure_mergeable_mr(merge_request)

    assert exc_info.value.message_key == 'SQUASH_AND_TRAILERS'


@patch.object(BatchMergeJob, 'get_mr_ci_status')
def test_ensure_mergeable_mr_ci_not_ok(bmj_get_mr_ci_status):
    batch_merge_job = get_batch_merge_job()
    batch_merge_job._options.requests_commit_tagging = True
    batch_merge_job._project.only_allow_merge_if_pipeline_succeeds = True
    bmj_get_mr_ci_status.return_value = 'failed'
    merge_request = Mock(
        assignee_id=batch_merge_job._user.id,
        state='opened',
        work_in_progress=False,
        squash=False,
    )
    merge_request.fetch_approvals.return_value.sufficient = True
    with pytest.raises(MergeError) as exc_info:
        batch_merge_job.ensure_mergeable_mr(merge_request)

    assert exc_info.value.message_key == 'CI_NOT_OK'


@patch.object(BatchMergeJob, 'get_source_project')
def test_fetch_mr_when_is_not_from_a_fork(bmj_get_source_project):
    batch_merge_job = get_batch_merge_job()
    merge_request = Mock()
    bmj_get_source_project.return_value = batch_merge_job._project
    with pytest.raises(AssertionError):
        batch_merge_job.fetch_mr(merge_request)
    batch_merge_job._repo.fetch.assert_not_called()


@patch.object(BatchMergeJob, 'get_source_project')
def test_fetch_mr_when_is_from_a_fork(bmj_get_source_project):
    batch_merge_job = get_batch_merge_job()
    merge_request = Mock()
    source_project = Mock()
    bmj_get_source_project.return_value = source_project

    batch_merge_job.fetch_mr(merge_request)

    batch_merge_job._repo.fetch.assert_called_once_with(
        remote='source',
        remote_url=source_project.ssh_url_to_repo,
    )


def test_fuse_branch_a_on_branch_b_using_rebase():
    batch_merge_job = get_batch_merge_job()
    batch_merge_job._options.use_merge_strategy = False
    branch_a = 'A'
    branch_b = 'B'

    batch_merge_job.fuse_branch_a_on_branch_b(branch_a, branch_b)

    batch_merge_job._repo.fuse.assert_called_once_with(
        'rebase',
        branch_a,
        branch_b,
    )


def test_fuse_branch_a_on_branch_b_using_merge():
    # FIXME: somehow fuse() is called twice,
    # Looks like 'get_batch_merge_job()' is cached or py.test fixture thing?
    batch_merge_job = get_batch_merge_job()
    batch_merge_job._repo.reset_mock()
    batch_merge_job._options.use_merge_strategy = True
    branch_a = 'A'
    branch_b = 'B'

    batch_merge_job.fuse_branch_a_on_branch_b(branch_a, branch_b)

    batch_merge_job._repo.fuse.assert_called_once_with(
        'merge',
        branch_a,
        branch_b,
    )


def test_push_batch():
    batch_merge_job = get_batch_merge_job()
    batch_merge_job.push_batch()
    batch_merge_job._repo.push.assert_called_once_with(
        BatchMergeJob.BATCH_BRANCH_NAME,
        force=True,
    )


def test_ensure_mr_not_changed():
    with patch('marge.batch_job.MergeRequest') as mr_class:
        batch_merge_job = get_batch_merge_job()
        merge_request = Mock()
        changed_merge_request = Mock()
        mr_class.fetch_by_iid.return_value = changed_merge_request

        with pytest.raises(MergeError) as exc_info:
            batch_merge_job.ensure_mr_not_changed(merge_request)
        assert exc_info.value.message_key == 'CHANGED'

        mr_class.fetch_by_iid.assert_called_once_with(
            merge_request.project_id,
            merge_request.iid,
            batch_merge_job._api,
        )


def test_fuse_mr_when_target_branch_was_moved():
    batch_merge_job = get_batch_merge_job()
    merge_request = Mock()
    with pytest.raises(AssertionError):
        batch_merge_job.fuse_mr(merge_request, 'abc')
    batch_merge_job._repo.fetch.assert_called_once_with('origin')
    batch_merge_job._repo.get_commit_hash.assert_called_once_with(
        'origin/%s' % merge_request.target_branch,
    )


def test_fuse_mr_when_source_branch_was_moved():
    batch_merge_job = get_batch_merge_job()
    batch_merge_job._repo.reset_mock()
    merge_request = Mock(source_project_id=batch_merge_job._project.id)

    sha = 'abc'
    # this will return 'abc' for both target and source branch
    # target is expected 'abc', but merge_request.sha is a mock so would not match
    batch_merge_job._repo.get_commit_hash.return_value = sha

    with pytest.raises(AssertionError):
        batch_merge_job.fuse_mr(merge_request, sha)
    batch_merge_job._repo.fetch.assert_called_once_with('origin')
    batch_merge_job._repo.get_commit_hash.assert_has_calls([
        call('origin/%s' % merge_request.target_branch),
        call('origin/%s' % merge_request.source_branch),
    ])


@patch.object(BatchMergeJob, 'fuse_branch_a_on_branch_b')
@patch.object(BatchMergeJob, 'add_trailers')
@patch.object(BatchMergeJob, 'get_source_project')
def test_fuse_mr(
    bmj_get_source_project,
    bmj_add_trailers,
    bmj_fuse_a_on_b,
):
    sha = 'abc'
    new_sha = 'abcd'
    batch_merge_job = get_batch_merge_job()
    batch_merge_job._repo.reset_mock()
    batch_merge_job._repo.get_commit_hash.return_value = sha
    merge_request = Mock(
        sha=sha,
        source_project_id=batch_merge_job._project.id,
    )
    bmj_fuse_a_on_b.return_value = new_sha
    bmj_add_trailers.return_value = new_sha
    bmj_get_source_project.return_value = batch_merge_job._project

    r_sha = batch_merge_job.fuse_mr(merge_request, sha)

    batch_merge_job._repo.fetch.assert_called_once_with('origin')
    batch_merge_job._repo.get_commit_hash.assert_has_calls([
        call('origin/%s' % merge_request.target_branch),
        call('origin/%s' % merge_request.source_branch),
    ])

    batch_merge_job._repo.checkout_branch.assert_has_calls([
        call(
            merge_request.source_branch,
            'origin/%s' % merge_request.source_branch,
        ),
        call(
            merge_request.target_branch,
            'origin/%s' % merge_request.target_branch,
        ),
    ])
    bmj_fuse_a_on_b.assert_has_calls([
        call(
            merge_request.source_branch,
            'origin/%s' % merge_request.target_branch,
        ),
        call(
            merge_request.target_branch,
            merge_request.source_branch,
        ),
    ])
    bmj_add_trailers.assert_called_once_with(merge_request)
    bmj_get_source_project.assert_called_once_with(merge_request)
    batch_merge_job._repo.push.assert_has_calls([
        call(
            merge_request.source_branch,
            None,
            force=True,
        ),
        call(merge_request.target_branch),
    ])
    assert r_sha == new_sha
