from unittest.mock import Mock, patch

import marge.bot
import marge.git
import marge.gitlab
from marge.merge_request import MergeRequest


def _merge_request_info(**override_fields):
    base_merge_request = {
        'id':  53,
        'iid': 54,
        'title': 'a title',
        'project_id': 1234,
        'assignee': {'id': 77},
        'state': 'opened',
        'sha': 'dead4g00d',
        'source_project_id': 5678,
        'target_project_id': 1234,
        'source_branch': 'useless_new_feature',
        'target_branch': 'master',
    }
    return dict(base_merge_request, **override_fields)


class TestRebaseAndAcceptMergeRequest(object):
    @patch('marge.gitlab.Api')
    def setup_method(self, _method, _api_class):
        bot = marge.bot.Bot(user_name='bot', auth_token='token', gitlab_url='url', project_path='some/project')
        assert not bot.connected

        bot.connect()
        assert bot.connected

        self.api = bot._api
        self.bot = bot

    @patch('time.sleep')
    @patch('marge.bot.push_rebased_version')
    def test_succeeds_first_time(self, time_sleep, push_rebased_version):
        merge_request =  MergeRequest(self.api, _merge_request_info())
        merge_request.accept = Mock()

        repo = Mock(marge.git.Repo)
        bot = self. bot
        bot.wait_for_ci_to_pass = Mock()
        bot.wait_for_branch_to_be_merged = Mock()
        marge.bot.push_rebased_version = Mock(return_value='new_sha')

        bot.rebase_and_accept_merge_request(merge_request, repo)

        marge.bot.push_rebased_version.assert_called_once_with(repo, 'useless_new_feature', 'master')
        bot.wait_for_ci_to_pass.assert_called_once_with('new_sha')
        merge_request.accept.assert_called_once_with(remove_branch=True, sha='new_sha')
        bot.wait_for_branch_to_be_merged.assert_called_once_with(merge_request)

    @patch('time.sleep')
    @patch('marge.bot.push_rebased_version')
    def test_succeeds_second_time(self, time_sleep, push_rebased_version):
        merge_request =  MergeRequest(self.api, _merge_request_info())
        merge_request.accept = Mock(side_effect=[marge.gitlab.NotAcceptable('blah'), None])

        repo = Mock(marge.git.Repo)
        bot = self. bot
        bot.wait_for_ci_to_pass = Mock()
        bot.wait_for_branch_to_be_merged = Mock()
        marge.bot.push_rebased_version = Mock(side_effect=['new_sha_1', 'new_sha_2'])

        bot.rebase_and_accept_merge_request(merge_request, repo)

        marge.bot.push_rebased_version.assert_called_with(repo, 'useless_new_feature', 'master')
        bot.wait_for_ci_to_pass.assert_any_call('new_sha_1')
        merge_request.accept.assert_any_call(remove_branch=True, sha='new_sha_1')
        bot.wait_for_ci_to_pass.assert_any_call('new_sha_2')
        merge_request.accept.assert_any_call(remove_branch=True, sha='new_sha_2')
        bot.wait_for_branch_to_be_merged.assert_called_once_with(merge_request)
