from unittest.mock import Mock, patch

import pytest

import marge.commit
import marge.bot
import marge.git
import marge.gitlab
import marge.job
import marge.project
import marge.user
from marge.merge_request import MergeRequest
from marge.approvals import Approvals

import tests.test_project as test_project
import tests.test_user as test_user


def _merge_request_info(**override_fields):
    base_merge_request = {
        'id':  53,
        'iid': 54,
        'title': 'a title',
        'project_id': 1234,
        'assignee': {'id': 77},
        'approved_by': [],
        'state': 'opened',
        'sha': 'dead4g00d',
        'source_project_id': 5678,
        'target_project_id': 1234,
        'source_branch': 'useless_new_feature',
        'target_branch': 'master',
        'work_in_progress': False,
        'web_url': 'http://git.example.com/group/project/merge_request/666',
    }
    return dict(base_merge_request, **override_fields)


class struct:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


_project_fetch_by_id = marge.project.Project.fetch_by_id
class TestRebaseAndAcceptMergeRequest(object):
    def teardown_method(self, _method):
        marge.project.Project.fetch_by_id = _project_fetch_by_id
    def setup_method(self, _method):
        marge.project.Project.fetch_by_id = Mock(return_value=struct(id=5678, ssh_url_to_repo='http://http://git.example.com/group/project.git', only_allow_merge_if_pipeline_succeeds=True))
        self.api = Mock(marge.gitlab.Api)
        self.api.version = Mock(return_value=marge.gitlab.Version.parse('9.2.3-ee'))

    def make_job(self, merge_request, options=None, user_is_admin=True):
        project = marge.project.Project(self.api, test_project.INFO)
        repo = Mock(marge.git.Repo)
        options = options or marge.job.MergeJobOptions.default()
        user = marge.user.User(self.api, dict(test_user.INFO, name='marge-bot', is_admin=user_is_admin))
        bot = marge.bot.Bot(
            api=self.api,
            user=user,
            ssh_key_file='id_rsa',
            add_reviewers=options.add_reviewers,
            add_tested=options.add_tested,
            impersonate_approvers=options.reapprove,
        )
        return marge.job.MergeJob(bot=bot, project=project, merge_request=merge_request, repo=repo)


    @patch('marge.job._get_reviewer_names_and_emails', return_value=[])
    @patch('marge.commit.Commit.last_on_branch', return_value=struct(id='af7a'))
    @patch('marge.commit.Commit.fetch_by_id', return_value=struct(status='success'))
    @patch('marge.job.push_rebased_and_rewritten_version', return_value=('505e', 'deadbeef', 'af7a'))
    @patch('time.sleep')
    def test_succeeds_first_time(self, time_sleep, push_rebased_and_rewritten_version, cfetch_by_id, last_on_branch, _get_reviewers):
        merge_request = MergeRequest(self.api, _merge_request_info())
        job = self.make_job(
            merge_request,
            marge.job.MergeJobOptions.default(add_tested=True, add_reviewers=False))

        merge_request.accept = Mock()

        job.wait_for_ci_to_pass = Mock()
        job.wait_for_branch_to_be_merged = Mock()
        approvals = Mock(Approvals)
        approvals.sufficient = True

        job.rebase_and_accept(approvals)

        marge.job.push_rebased_and_rewritten_version.assert_called_once_with(
            repo=job.repo,
            source_branch='useless_new_feature',
            target_branch='master',
            reviewers=None,
            tested_by=['marge-bot <http://git.example.com/group/project/merge_request/666>'],
            source_repo_url='http://http://git.example.com/group/project.git',
        )
        job.wait_for_ci_to_pass.assert_called_once_with(5678, 'af7a')
        merge_request.accept.assert_called_once_with(remove_branch=True, sha='af7a')
        job.wait_for_branch_to_be_merged.assert_called_once_with()

    @patch('marge.job._get_reviewer_names_and_emails', return_value=[])
    @patch('marge.commit.Commit.last_on_branch', return_value=struct(id='af7a'))
    @patch('marge.commit.Commit.fetch_by_id', return_value=struct(status='success'))
    @patch('marge.job.push_rebased_and_rewritten_version', side_effect=[
        ('505e', 'deadbeef', 'af7a'),
        ('505e2', 'deadbeef2', 'af7a2'),
    ])
    @patch('time.sleep')
    def test_fails_on_not_acceptable_if_master_did_not_move(self, time_sleep, push_rebased_and_rewritten_version, fetch_by_id, last_on_branch, _get_reviewers):
        merge_request = MergeRequest(self.api, _merge_request_info())
        merge_request.accept = Mock(side_effect=[marge.gitlab.NotAcceptable('blah'), None])
        job = self.make_job(merge_request)

        repo = job.repo
        job.wait_for_ci_to_pass = Mock()
        job.wait_for_branch_to_be_merged = Mock()
        approvals = Mock(Approvals)

        expected_message = "Someone pushed to branch while we were trying to merge"
        with pytest.raises(marge.job.CannotMerge, message=expected_message):
            job.rebase_and_accept(approvals)

    @patch('marge.job._get_reviewer_names_and_emails', return_value=[])
    @patch('marge.commit.Commit.fetch_by_id', return_value=struct(status='success'))
    @patch('time.sleep')
    def test_succeeds_second_time_if_master_moved(self, time_sleep, last_on_branch, _get_reviewers):
        merge_request = MergeRequest(self.api, _merge_request_info())
        merge_request.accept = Mock(side_effect=[marge.gitlab.NotAcceptable('blah'), None])
        job = self.make_job(
            merge_request,
            options=marge.job.MergeJobOptions.default(add_tested=True, add_reviewers=True),
        )

        repo = job.repo
        repo.project_id = 5678

        job.wait_for_ci_to_pass = Mock()
        job.wait_for_branch_to_be_merged = Mock()

        approvals = Mock(Approvals)

        commit = struct
        after_rebase_head = commit(id='af7a')
        after_second_rebase_head = commit(id='d1ff3')
        original_master = commit(id='3243')
        moved_master = commit(id='505e2')

        def _make_fake_last_on_branch():
            ids = {
                'useless_new_feature': [after_rebase_head, after_second_rebase_head],
                'master': [moved_master, moved_master],
            }

            def _fake_last_on_branch(_project, branch, _api):
                return ids[branch].pop(0)

            return _fake_last_on_branch

        with patch('marge.commit.Commit.last_on_branch', side_effect=_make_fake_last_on_branch()), \
             patch('marge.job.push_rebased_and_rewritten_version', side_effect=[
                  (original_master.id, 'deadbeef', after_rebase_head.id),
                  (moved_master.id, 'deadbeef2', after_second_rebase_head.id),
             ]):
            job.rebase_and_accept(approvals)

            marge.job.push_rebased_and_rewritten_version.assert_called_with(
                repo=repo,
                source_branch='useless_new_feature',
                target_branch='master',
                source_repo_url='http://http://git.example.com/group/project.git',
                reviewers=[],
                tested_by=['marge-bot <http://git.example.com/group/project/merge_request/666>'],
            )

            job.wait_for_ci_to_pass.assert_any_call(5678, after_rebase_head.id)
            merge_request.accept.assert_any_call(remove_branch=True, sha=after_rebase_head.id)
            job.wait_for_ci_to_pass.assert_any_call(5678, after_second_rebase_head.id)
            merge_request.accept.assert_any_call(remove_branch=True, sha=after_second_rebase_head.id)
            job.wait_for_branch_to_be_merged.assert_called_once_with()

    @patch('marge.job.push_rebased_and_rewritten_version')
    @patch('time.sleep')
    def test_wont_merge_wip_stuff(self, time_sleep, push_rebased_and_rewritten_version):
        merge_request = MergeRequest(self.api, _merge_request_info(work_in_progress=True))
        job = self.make_job(merge_request)

        expected_message = "Sorry, I can't merge requests marked as Work-In-Progress!"
        with pytest.raises(marge.job.CannotMerge, message=expected_message):
            job.rebase_and_accept(Mock(Approvals))
