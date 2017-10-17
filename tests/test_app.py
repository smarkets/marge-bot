import contextlib
import datetime
import os
import re
import shlex
import unittest.mock as mock
from functools import wraps

import pytest

import marge.app as app
import marge.bot as bot
import marge.interval as interval
import marge.job as job

import tests.gitlab_api_mock as gitlab_mock
from tests.test_user import INFO as user_info


@contextlib.contextmanager
def env(**kwargs):
    original = os.environ.copy()

    os.environ.clear()
    for k, v in kwargs.items():
        os.environ[k] = v

    yield

    os.environ.clear()
    for k, v in original.items():
        os.environ[k] = v


@contextlib.contextmanager
def main(cmdline=''):
    def api_mock(gitlab_url, auth_token):
        assert gitlab_url == 'http://foo.com'
        assert auth_token in ('NON-ADMIN-TOKEN', 'ADMIN-TOKEN')
        api = gitlab_mock.Api(gitlab_url=gitlab_url, auth_token=auth_token, initial_state='initial')
        user_info_for_token = dict(user_info, is_admin=auth_token == 'ADMIN-TOKEN')
        api.add_user(user_info_for_token, is_current=True)
        return api

    class DoNothingBot(bot.Bot):
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

def test_embargo():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main('--embargo="Fri 1pm-Mon 7am"') as bot:
            assert bot.config.merge_opts == job.MergeJobOptions.default(
               embargo=interval.IntervalUnion.from_human('Fri 1pm-Mon 7am'),
            )

def test_add_tested():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main('--add-tested') as bot:
            assert bot.config.merge_opts != job.MergeJobOptions.default()
            assert bot.config.merge_opts == job.MergeJobOptions.default(add_tested=True)

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


def test_impersonate_approvers():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with pytest.raises(AssertionError):
            with main('--impersonate-approvers') as bot:
                pass

    with env(MARGE_AUTH_TOKEN="ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main('--impersonate-approvers') as bot:
            assert bot.config.merge_opts != job.MergeJobOptions.default()
            assert bot.config.merge_opts == job.MergeJobOptions.default(reapprove=True)


def test_project_regexp():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main("--project-regexp='foo.*bar'") as bot:
            assert bot.config.project_regexp == re.compile('foo.*bar')

def test_ci_timeout():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main("--ci-timeout 5m") as bot:
            assert bot.config.merge_opts != job.MergeJobOptions.default()
            assert bot.config.merge_opts == job.MergeJobOptions.default(ci_timeout=datetime.timedelta(seconds=5*60))

def test_deprecated_max_ci_time_in_minutes():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main("--max-ci-time-in-minutes=5") as bot:
            assert bot.config.merge_opts != job.MergeJobOptions.default()
            assert bot.config.merge_opts == job.MergeJobOptions.default(ci_timeout=datetime.timedelta(seconds=5*60))

def test_git_timeout():
    with env(MARGE_AUTH_TOKEN="NON-ADMIN-TOKEN", MARGE_SSH_KEY="KEY", MARGE_GITLAB_URL='http://foo.com'):
        with main("--git-timeout '150 s'") as bot:
            assert bot.config.git_timeout == datetime.timedelta(seconds=150)


# FIXME: I'd reallly prefer this to be a doctest, but adding --doctest-modules
# seems to seriously mess up the test run
def test_time_interval():
    _900s = datetime.timedelta(0, 900)
    assert [app.time_interval(x) for x in ['15min', '15m', '.25h', '900s']] == [_900s] * 4
