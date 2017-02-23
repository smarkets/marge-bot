import os
import shlex
import subprocess
import unittest.mock as mock

import pytest

import marge.git


@mock.patch('marge.git._run')
class TestRepo(object):
    def setup_method(self, _method):
        self.repo = marge.git.Repo(
            remote_url='ssh://git@git.foo.com/some/repo.git',
            local_path='/tmp/local/path',
            ssh_key_file=None,
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
        success = self.repo.rebase('feature_branch', 'master_of_the_universe')
        assert success

        assert get_calls(mocked_run) == [
            'git -C /tmp/local/path fetch origin',
            'git -C /tmp/local/path checkout feature_branch',
            'git -C /tmp/local/path rebase origin/master_of_the_universe',
        ]

    def test_rebase_failure(self, mocked_run):
        def fail_on_rebase(*args, **kwargs):
            if 'rebase' in args and '--abort' not in args:
                raise subprocess.CalledProcessError(returncode=1, cmd='git rebase blah')

        mocked_run.side_effect = fail_on_rebase

        success = self.repo.rebase('feature_branch', 'master_of_the_universe')
        assert not success

        assert get_calls(mocked_run) == [
            'git -C /tmp/local/path fetch origin',
            'git -C /tmp/local/path checkout feature_branch',
            'git -C /tmp/local/path rebase origin/master_of_the_universe',
            'git -C /tmp/local/path rebase --abort',
        ]

    def test_rebase_same_branch(self, mocked_run):
        with pytest.raises(AssertionError):
            self.repo.rebase('branch', 'branch')

        assert get_calls(mocked_run) == []

    def test_remove_branch(self, mocked_run):
        self.repo.remove_branch('some_branch')
        assert get_calls(mocked_run) == [
            'git -C /tmp/local/path checkout master',
            'git -C /tmp/local/path branch -D some_branch',
        ]

    def test_remove_master_branch_fails(self, mocked_run):
        with pytest.raises(AssertionError):
            self.repo.remove_branch('master')

    def test_push_force(self, mocked_run):
        self.repo.push_force('my_branch')
        assert get_calls(mocked_run) == [
            'git -C /tmp/local/path checkout my_branch',
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
            'git -C /tmp/local/path checkout my_branch',
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
            'git -C /tmp/local/path checkout my_branch',
            'git -C /tmp/local/path diff-index --quiet HEAD',
            'git -C /tmp/local/path ls-files --others',
        ]

    def test_get_head_commit_hash(self, mocked_run):
        mocked_run.return_value = mocked_stdout(b'deadbeef')

        hash = self.repo.get_head_commit_hash()
        assert hash == 'deadbeef'

        assert get_calls(mocked_run) == [
            'git -C /tmp/local/path rev-parse HEAD',
        ]


    def test_passes_ssh_key(self, mocked_run):
        repo = self.repo._replace(ssh_key_file='/foo/id_rsa')
        repo.config_user_info('bart', 'bart@gmail.com')
        assert get_calls(mocked_run) == [
            "GIT_SSH_COMMAND='ssh -i /foo/id_rsa' git -C /tmp/local/path config user.email bart@gmail.com",
            "GIT_SSH_COMMAND='ssh -i /foo/id_rsa' git -C /tmp/local/path config user.name bart",
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
