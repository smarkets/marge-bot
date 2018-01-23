import datetime
import os
import re
import shlex
import subprocess
import unittest.mock as mock

import pytest

import marge.git
from marge.git import GIT_SSH_COMMAND


@mock.patch('marge.git._run')
class TestRepo(object):
    def setup_method(self, _method):
        self.repo = marge.git.Repo(
            remote_url='ssh://git@git.foo.com/some/repo.git',
            local_path='/tmp/local/path',
            ssh_key_file=None,
            timeout=datetime.timedelta(seconds=1),
        )

    def test_clone(self, mocked_run):
        self.repo.clone()
        assert get_calls(mocked_run) == [
            'git clone --origin=origin ssh://git@git.foo.com/some/repo.git /tmp/local/path',
        ]

    def test_config_user_info(self, mocked_run):
        self.repo.config_user_info('bart', 'bart.simpson@gmail.com')
        assert get_calls(mocked_run) == [
            'git -C /tmp/local/path config user.email bart.simpson@gmail.com',
            'git -C /tmp/local/path config user.name bart',
        ]

    def test_rebase_success(self, mocked_run):
        self.repo.rebase('feature_branch', 'master_of_the_universe')

        assert get_calls(mocked_run) == [
            'git -C /tmp/local/path fetch origin',
            'git -C /tmp/local/path checkout -B feature_branch origin/feature_branch --',
            'git -C /tmp/local/path rebase origin/master_of_the_universe',
            'git -C /tmp/local/path rev-parse HEAD'
        ]

    def test_merge_success(self, mocked_run):
        self.repo.merge('feature_branch', 'master_of_the_universe')

        assert get_calls(mocked_run) == [
            'git -C /tmp/local/path fetch origin',
            'git -C /tmp/local/path checkout -B feature_branch origin/feature_branch --',
            'git -C /tmp/local/path merge origin/master_of_the_universe',
            'git -C /tmp/local/path rev-parse HEAD'
        ]

    def test_reviewer_tagging_success(self, mocked_run):
        self.repo.tag_with_trailer(
            trailer_name='Reviewed-by',
            trailer_values=['John Simon <john@invalid>'],
            branch='feature_branch',
            start_commit='origin/master_of_the_universe',
        )

        rewrite, parse = get_calls(mocked_run)
        assert re.match('git -C /tmp/local/path filter-branch --force --msg-filter.*John Simon <john@invalid>.*origin/master_of_the_universe..feature_branch', rewrite)
        assert parse == 'git -C /tmp/local/path rev-parse HEAD'

    def test_reviewer_tagging_failure(self, mocked_run):
        def fail_on_filter_branch(*args, **kwargs):
            if 'filter-branch' in args:
                raise subprocess.CalledProcessError(returncode=1, cmd='git rebase blah')
            elif 'rev-parse' in args or 'reset' in args:
                return mock.Mock()
            else:
                raise Exception('Unexpected call:', args)

        mocked_run.side_effect = fail_on_filter_branch

        try:
            sha = self.repo.tag_with_trailer(
                trailer_name='Reviewed-by',
                branch='feature_branch',
                start_commit='origin/master_of_the_universe',
                trailer_values=['John Simon <john@invalid.com>']
            )
        except marge.git.GitError:
            pass
        else:
            assert False
        rewrite, check, abort = get_calls(mocked_run)
        assert 'filter-branch' in rewrite
        assert check == 'git -C /tmp/local/path rev-parse refs/original/refs/heads/'
        assert abort == 'git -C /tmp/local/path reset --hard refs/original/refs/heads/feature_branch'

    def test_rebase_same_branch(self, mocked_run):
        with pytest.raises(AssertionError):
            self.repo.rebase('branch', 'branch')

        assert get_calls(mocked_run) == []

    def test_merge_same_branch(self, mocked_run):
        with pytest.raises(AssertionError):
            self.repo.merge('branch', 'branch')

        assert get_calls(mocked_run) == []

    def test_remove_branch(self, mocked_run):
        self.repo.remove_branch('some_branch')
        assert get_calls(mocked_run) == [
            'git -C /tmp/local/path checkout master --',
            'git -C /tmp/local/path branch -D some_branch',
        ]

    def test_remove_master_branch_fails(self, mocked_run):
        with pytest.raises(AssertionError):
            self.repo.remove_branch('master')

    def test_push_force(self, mocked_run):
        mocked_run.return_value = mocked_stdout(b'')
        self.repo.push_force('my_branch')
        assert get_calls(mocked_run) == [
            'git -C /tmp/local/path checkout my_branch --',
            'git -C /tmp/local/path diff-index --quiet HEAD',
            'git -C /tmp/local/path ls-files --others',
            'git -C /tmp/local/path push --force origin my_branch',
        ]

    def test_push_force_fails_on_dirty(self, mocked_run):
        def fail_on_diff_index(*args, **kwargs):
            if 'diff-index' in args:
                raise subprocess.CalledProcessError(returncode=1, cmd='git diff-index blah')
        mocked_run.side_effect = fail_on_diff_index

        with pytest.raises(marge.git.GitError):
            self.repo.push_force('my_branch')

        assert get_calls(mocked_run) == [
            'git -C /tmp/local/path checkout my_branch --',
            'git -C /tmp/local/path diff-index --quiet HEAD',
        ]

    def test_push_force_fails_on_untracked(self, mocked_run):
        def fail_on_ls_files(*args, **kwargs):
            if 'ls-files' in args:
                return mocked_stdout('some_file.txt\nanother_file.py')

        mocked_run.side_effect = fail_on_ls_files

        with pytest.raises(marge.git.GitError):
            self.repo.push_force('my_branch')

        assert get_calls(mocked_run) == [
            'git -C /tmp/local/path checkout my_branch --',
            'git -C /tmp/local/path diff-index --quiet HEAD',
            'git -C /tmp/local/path ls-files --others',
        ]

    def test_get_commit_hash(self, mocked_run):
        mocked_run.return_value = mocked_stdout(b'deadbeef')

        hash = self.repo.get_commit_hash()
        assert hash == 'deadbeef'

        assert get_calls(mocked_run) == [
            'git -C /tmp/local/path rev-parse HEAD',
        ]
        self.repo.get_commit_hash(rev='master')
        assert get_calls(mocked_run)[-1] == 'git -C /tmp/local/path rev-parse master'




    def test_passes_ssh_key(self, mocked_run):
        repo = self.repo._replace(ssh_key_file='/foo/id_rsa')
        repo.config_user_info('bart', 'bart@gmail.com')
        assert get_calls(mocked_run) == [
            "GIT_SSH_COMMAND='%s -F /dev/null -o IdentitiesOnly=yes -i /foo/id_rsa' git -C /tmp/local/path config user.email bart@gmail.com" % GIT_SSH_COMMAND,
            "GIT_SSH_COMMAND='%s -F /dev/null -o IdentitiesOnly=yes -i /foo/id_rsa' git -C /tmp/local/path config user.name bart" % GIT_SSH_COMMAND,
        ]

def get_calls(mocked_run):
    return [bashify(call) for call in mocked_run.call_args_list]

def bashify(call):
    args, kwargs = call
    args = [shlex.quote(arg) for arg in args]
    env = kwargs.get('env') or {}
    alt_env = [shlex.quote(k) + '=' + shlex.quote(v) for k,v in set(env.items()) - set(os.environ.items())]
    return ' '.join(alt_env + args)

def mocked_stdout(stdout):
    return subprocess.CompletedProcess(['blah', 'args'], 0, stdout, None)



def _filter_test(s, trailer_name, trailer_values):
    script = marge.git._filter_branch_script(trailer_name, trailer_values)
    result = subprocess.check_output(
        [b'sh', b'-c', script.encode('utf-8')],
        input=s.encode('utf-8'),
        stderr=subprocess.STDOUT
    )
    return result.decode('utf-8')


def test_filter():
    assert _filter_test('Some Stuff', 'Tested-by', []) == 'Some Stuff\n'
    assert _filter_test('Some Stuff\n', 'Tested-by', []) == 'Some Stuff\n'
    assert _filter_test('Some Stuff', 'Tested-by', ['T. Estes <testes@example.com>']) == '''Some Stuff

Tested-by: T. Estes <testes@example.com>
'''

    test_commit_message=r'''Fix: bug in BLah.

Some stuff.
Some More stuff (really? Yeah: really!)

Reviewed-by: R. Viewer <rviewer@example.com>
Reviewed-by: R. Viewer <rviewer@example.com>
Signed-off-by: Stephen Offer <soffer@example.com>
'''
    with_tested_by = _filter_test(test_commit_message, 'Tested-by', ['T. Estes <testes@example.com>'])
    assert with_tested_by == '''Fix: bug in BLah.

Some stuff.
Some More stuff (really? Yeah: really!)

Reviewed-by: R. Viewer <rviewer@example.com>
Signed-off-by: Stephen Offer <soffer@example.com>
Tested-by: T. Estes <testes@example.com>
'''
    with_new_reviewed_by = _filter_test(with_tested_by, 'Reviewed-by', [
        'Roger Ebert <ebert@example.com>', 'John Simon <simon@example.com>'
    ])
    assert with_new_reviewed_by == '''Fix: bug in BLah.

Some stuff.
Some More stuff (really? Yeah: really!)

Signed-off-by: Stephen Offer <soffer@example.com>
Tested-by: T. Estes <testes@example.com>
Reviewed-by: Roger Ebert <ebert@example.com>
Reviewed-by: John Simon <simon@example.com>
'''
    assert _filter_test('Test: frobnificator', 'Tested-by', []) == 'Test: frobnificator\n'
    assert _filter_test('Test: frobnificator', 'Tested-by', ['T. Estes <testes@example.com>']) == (
        '''Test: frobnificator

Tested-by: T. Estes <testes@example.com>
'''
    )


def test_filter_fails_on_empty_commit_messages():
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        _filter_test('', '', [])
    assert exc_info.value.output == b'ERROR: Expected a non-empty commit message'


def test_filter_fails_on_commit_messages_that_are_empty_apart_from_trailers():
    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        _filter_test(
            'Tested-by: T. Estes <testes@example.com>',
            'Tested-by',
            ['T. Estes <testes@example.com>']
        )
    assert exc_info.value.output == b'ERROR: Your commit message seems to consist only of Trailers: Tested-by: T. Estes <testes@example.com>'

    with pytest.raises(subprocess.CalledProcessError) as exc_info:
        _filter_test('', 'Tested-by', ['T. Estes <testes@example.com>'])
    assert exc_info.value.output == b'ERROR: Expected a non-empty commit message'


def test_filter_treats_the_first_commit_line_not_as_a_trailer_unless_it_matches_the_trailer_name_passed_in():
    _filter_test(
        'Tested-by: T. Estes <testes@example.com>',
        'Reviewed-by', ['Reviewed-by: John Simon <john@invalid>']
    ) == 'Tested-by: T. Estes <testes@example.com>'
