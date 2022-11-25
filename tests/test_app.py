import contextlib
import datetime
import os
import re
import shlex
import tempfile
import unittest.mock as mock

import pytest

import marge.app as app
import marge.bot as bot_module
import marge.interval as interval
import marge.job as job

import tests.gitlab_api_mock as gitlab_mock
from tests.test_user import INFO as user_info


@contextlib.contextmanager
def config_file():
    content = '''
add-part-of: true
add-reviewers: true
add-tested: true
branch-regexp: foo.*bar
ci-timeout: 5min
embargo: Friday 1pm - Monday 7am
git-timeout: 150s
gitlab-url: "http://foo.com"
impersonate-approvers: true
project-regexp: foo.*bar
ssh-key: KEY
'''
    with tempfile.NamedTemporaryFile(mode='w', prefix='config-file-') as tmp_config_file:
        try:
            tmp_config_file.write(content)
            tmp_config_file.flush()
            yield tmp_config_file.name
        finally:
            tmp_config_file.close()


@contextlib.contextmanager
def env(**kwargs):
    original = os.environ.copy()

    os.environ.clear()
    for key, value in kwargs.items():
        os.environ[key] = value

    yield

    os.environ.clear()
    for key, value in original.items():
        os.environ[key] = value


@contextlib.contextmanager
def main(cmdline=''):
    def api_mock(gitlab_url, auth_token):
        assert gitlab_url == 'http://foo.com'
        assert auth_token in ('NON-ADMIN-TOKEN', 'ADMIN-TOKEN')
        api = gitlab_mock.Api(gitlab_url=gitlab_url, auth_token=auth_token, initial_state='initial')
        user_info_for_token = dict(user_info, is_admin=auth_token == 'ADMIN-TOKEN')
        api.add_user(user_info_for_token, is_current=True)
        api.add_transition(gitlab_mock.GET('/version'), gitlab_mock.Ok({'version': '11.6.0-ce'}))
        return api

    class DoNothingBot(bot_module.Bot):
        instance = None

        def start(self):
            assert self.__class__.instance is None
            self.__class__.instance = self

        @property
        def config(self):
            return self._config

    with mock.patch('marge.bot.Bot', new=DoNothingBot), mock.patch('marge.gitlab.Api', new=api_mock):
        app.main(args=shlex.split(cmdline))
        the_bot = DoNothingBot.instance
        assert the_bot is not None
        yield the_bot


def test_default_values():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main() as bot:
            assert bot.user.info == user_info
            assert bot.config.project_regexp == re.compile('.*')
            assert bot.config.git_timeout == datetime.timedelta(seconds=120)
            assert bot.config.merge_opts == job.MergeJobOptions.default()
            assert bot.config.merge_order == 'created_at'


def test_embargo():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main('--embargo="Fri 1pm-Mon 7am"') as bot:
            assert bot.config.merge_opts == job.MergeJobOptions.default(
                embargo=interval.IntervalUnion.from_human('Fri 1pm-Mon 7am'),
            )


def test_rebase_remotely():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main('--rebase-remotely') as bot:
            assert bot.config.merge_opts != job.MergeJobOptions.default()
            assert bot.config.merge_opts == job.MergeJobOptions.default(fusion=job.Fusion.gitlab_rebase)


def test_use_merge_strategy():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main('--use-merge-strategy') as bot:
            assert bot.config.merge_opts != job.MergeJobOptions.default()
            assert bot.config.merge_opts == job.MergeJobOptions.default(fusion=job.Fusion.merge)


def test_add_tested():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main('--add-tested') as bot:
            assert bot.config.merge_opts != job.MergeJobOptions.default()
            assert bot.config.merge_opts == job.MergeJobOptions.default(add_tested=True)


def test_use_merge_strategy_and_add_tested_are_mutually_exclusive():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with pytest.raises(app.MargeBotCliArgError):
            with main('--use-merge-strategy --add-tested'):
                pass


def test_add_part_of():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main('--add-part-of') as bot:
            assert bot.config.merge_opts != job.MergeJobOptions.default()
            assert bot.config.merge_opts == job.MergeJobOptions.default(add_part_of=True)


def test_add_reviewers():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with pytest.raises(AssertionError):
            with main('--add-reviewers') as bot:
                pass

    with env(MARGE_AUTH_TOKEN="ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main('--add-reviewers') as bot:
            assert bot.config.merge_opts != job.MergeJobOptions.default()
            assert bot.config.merge_opts == job.MergeJobOptions.default(add_reviewers=True)


def test_rebase_remotely_option_conflicts():
    for conflicting_flag in ['--use-merge-strategy', '--add-tested', '--add-part-of', '--add-reviewers']:
        with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
            with pytest.raises(app.MargeBotCliArgError):
                with main('--rebase-remotely %s' % conflicting_flag):
                    pass


def test_impersonate_approvers():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with pytest.raises(AssertionError):
            with main('--impersonate-approvers'):
                pass

    with env(MARGE_AUTH_TOKEN="ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main('--impersonate-approvers') as bot:
            assert bot.config.merge_opts != job.MergeJobOptions.default()
            assert bot.config.merge_opts == job.MergeJobOptions.default(reapprove=True)


def test_approval_reset_timeout():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main('--approval-reset-timeout 1m') as bot:
            assert bot.config.merge_opts != job.MergeJobOptions.default()
            assert bot.config.merge_opts == job.MergeJobOptions.default(
                approval_timeout=datetime.timedelta(seconds=60),
            )


def test_project_regexp():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main("--project-regexp='foo.*bar'") as bot:
            assert bot.config.project_regexp == re.compile('foo.*bar')


def test_ci_timeout():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main("--ci-timeout 5m") as bot:
            assert bot.config.merge_opts != job.MergeJobOptions.default()
            assert bot.config.merge_opts == job.MergeJobOptions.default(
                ci_timeout=datetime.timedelta(seconds=5*60),
            )


def test_deprecated_max_ci_time_in_minutes():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main("--max-ci-time-in-minutes=5") as bot:
            assert bot.config.merge_opts != job.MergeJobOptions.default()
            assert bot.config.merge_opts == job.MergeJobOptions.default(
                ci_timeout=datetime.timedelta(seconds=5*60),
            )


def test_git_timeout():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main("--git-timeout '150 s'") as bot:
            assert bot.config.git_timeout == datetime.timedelta(seconds=150)


def test_branch_regexp():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main("--branch-regexp='foo.*bar'") as bot:
            assert bot.config.branch_regexp == re.compile('foo.*bar')


def test_source_branch_regexp():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main("--source-branch-regexp='foo.*bar'") as bot:
            assert bot.config.source_branch_regexp == re.compile('foo.*bar')


def test_git_reference_repo():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main("--git-reference-repo='/foo/reference_repo'") as bot:
            assert bot.config.git_reference_repo == '/foo/reference_repo'


def test_merge_order_updated():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main("--merge-order='updated_at'") as bot:
            assert bot.config.merge_order == 'updated_at'


def test_merge_order_assigned():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main("--merge-order='assigned_at'") as bot:
            assert bot.config.merge_order == 'assigned_at'


# FIXME: I'd really prefer this to be a doctest, but adding --doctest-modules
# seems to seriously mess up the test run
def test_time_interval():
    _900s = datetime.timedelta(0, 900)
    assert [app.time_interval(x) for x in ['15min', '15m', '.25h', '900s']] == [_900s] * 4


def test_disabled_auth_token_cli_arg():
    with env(MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with pytest.raises(app.MargeBotCliArgError):
            with main('--auth-token=ADMIN-TOKEN'):
                pass


def test_disabled_ssh_key_cli_arg():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_GITLAB_URL='http://foo.com'):
        with pytest.raises(app.MargeBotCliArgError):
            with main('--ssh-key=KEY'):
                pass


def test_config_file():
    with config_file() as config_file_name:
        with env(MARGE_AUTH_TOKEN="ADMIN-TOKEN"):
            with main('--config-file=%s' % config_file_name) as bot:
                admin_user_info = dict(**user_info)
                admin_user_info['is_admin'] = True
                assert bot.user.info == admin_user_info
                assert bot.config.merge_opts != job.MergeJobOptions.default()
                assert bot.config.merge_opts == job.MergeJobOptions.default(
                    embargo=interval.IntervalUnion.from_human('Fri 1pm-Mon 7am'),
                    add_tested=True,
                    add_part_of=True,
                    add_reviewers=True,
                    reapprove=True,
                    ci_timeout=datetime.timedelta(seconds=5*60),
                )
                assert bot.config.project_regexp == re.compile('foo.*bar')
                assert bot.config.git_timeout == datetime.timedelta(seconds=150)
                assert bot.config.branch_regexp == re.compile('foo.*bar')


def test_config_overwrites():
    with config_file() as config_file_name:
        with env(MARGE_CI_TIMEOUT='20min', MARGE_AUTH_TOKEN="ADMIN-TOKEN"):
            with main('--git-timeout=100s --config-file=%s' % config_file_name) as bot:
                admin_user_info = dict(**user_info)
                admin_user_info['is_admin'] = True
                assert bot.user.info == admin_user_info
                assert bot.config.merge_opts != job.MergeJobOptions.default()
                assert bot.config.merge_opts == job.MergeJobOptions.default(
                    embargo=interval.IntervalUnion.from_human('Fri 1pm-Mon 7am'),
                    add_tested=True,
                    add_part_of=True,
                    add_reviewers=True,
                    reapprove=True,
                    ci_timeout=datetime.timedelta(seconds=20*60),
                )
                assert bot.config.project_regexp == re.compile('foo.*bar')
                assert bot.config.git_timeout == datetime.timedelta(seconds=100)
                assert bot.config.branch_regexp == re.compile('foo.*bar')
