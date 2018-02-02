import logging as log
import shlex
import os
import subprocess
from subprocess import PIPE, TimeoutExpired

from collections import namedtuple


from . import trailerfilter

# Turning off StrictHostKeyChecking is a nasty hack to approximate
# just accepting the hostkey sight unseen the first time marge
# connects. The proper solution would be to pass in known_hosts as
# a commandline parameter, but in practice few people will bother anyway and
# in this case the threat of MiTM seems somewhat bogus.
GIT_SSH_COMMAND = "ssh -o StrictHostKeyChecking=no "

def _filter_branch_script(trailer_name, trailer_values):
    filter_script = 'TRAILERS={trailers} python3 {script}'.format(
        trailers=shlex.quote(
            '\n'.join(
                '{}: {}'.format(trailer_name, trailer_value)
                for trailer_value in trailer_values or [''])
        ),
        script=trailerfilter.__file__,
    )
    return filter_script


class Repo(namedtuple('Repo', 'remote_url local_path ssh_key_file timeout')):
    def clone(self):
        self.git('clone', '--origin=origin', self.remote_url, self.local_path, from_repo=False)

    def config_user_info(self, user_name, user_email):
        self.git('config', 'user.email', user_email)
        self.git('config', 'user.name', user_name)

    def tag_with_trailer(self, trailer_name, trailer_values, branch, start_commit):
        """Replace `trailer_name` in commit messages with `trailer_values` in `branch` from `start_commit`.
        """

        # Strips all `$trailer_name``: lines and trailing newlines, adds an empty
        # newline and tags on the `$trailer_name: $trailer_value` for each `trailer_value` in
        # `trailer_values`.
        filter_script = _filter_branch_script(trailer_name, trailer_values)
        commit_range = start_commit + '..' + branch
        try:
            # --force = overwrite backup of last filter-branch
            self.git('filter-branch', '--force', '--msg-filter', filter_script, commit_range)
        except GitError:
            log.warning('filter-branch failed, will try to restore')
            try:
                self.get_commit_hash('refs/original/refs/heads/')
            except GitError:
                log.warning('No changes have been effected by filter-branch')
            else:
                self.git('reset', '--hard', 'refs/original/refs/heads/' + branch)
            raise
        return self.get_commit_hash()

    def merge(self, source_branch, target_branch, source_repo_url=None):
        """Merge `target_branch` into `source_branch` and return the new HEAD commit id.

        By default `source_branch` and `target_branch` are assumed to reside in the same
        repo as `self`. However, if `source_repo_url` is passed and not `None`,
        `source_branch` is taken from there.

        Throws a `GitError` if the merge fails. Will also try to --abort it.
        """
        return self._fuse_branch('merge', source_branch, target_branch, source_repo_url)

    def rebase(self, branch, new_base, source_repo_url=None):
        """Rebase `new_base` into `branch` and return the new HEAD commit id.

        By default `branch` and `new_base` are assumed to reside in the same
        repo as `self`. However, if `source_repo_url` is passed and not `None`,
        `branch` is taken from there.

        Throws a `GitError` if the rebase fails. Will also try to --abort it.
        """
        return self._fuse_branch('rebase', branch, new_base, source_repo_url)

    def _fuse_branch(self, strategy, branch, target_branch, source_repo_url=None):
        assert source_repo_url or branch != target_branch, branch

        self.git('fetch', '--prune', 'origin')
        if source_repo_url:
            # "upsert" remote 'source' and fetch it
            try:
                self.git('remote', 'rm', 'source')
            except GitError:
                pass
            self.git('remote', 'add', 'source', source_repo_url)
            self.git('fetch', '--prune', 'source')
            self.git('checkout', '-B', branch, 'source/' + branch, '--')
        else:
            self.git('checkout', '-B', branch, 'origin/' + branch, '--')

        try:
            self.git(strategy, 'origin/' + target_branch)
        except GitError:
            log.warning(strategy + ' failed, doing an --abort')
            self.git(strategy, '--abort')
            raise
        return self.get_commit_hash()

    def remove_branch(self, branch):
        assert branch != 'master'
        self.git('checkout', 'master', '--')
        self.git('branch', '-D', branch)

    def push_force(self, branch, source_repo_url=None):
        self.git('checkout', branch, '--')

        self.git('diff-index', '--quiet', 'HEAD')  # check it is not dirty

        untracked_files = self.git('ls-files', '--others').stdout  # check no untracked files
        if untracked_files:
            raise GitError('There are untracked files', untracked_files)

        if source_repo_url:
            assert self.get_remote_url('source') == source_repo_url
            source = 'source'
        else:
            source = 'origin'
        self.git('push', '--force', source, branch)

    def get_commit_hash(self, rev='HEAD'):
        """Return commit hash for `rev` (default "HEAD")."""
        result = self.git('rev-parse', rev)
        return result.stdout.decode('ascii').strip()

    def get_remote_url(self, name):
        return self.git('config', '--get', 'remote.{}.url'.format(name)).stdout.decode('utf-8').strip()

    def git(self, *args, from_repo=True):
        env = None
        if self.ssh_key_file:
            env = os.environ.copy()
            # ssh's handling of identity files is infuriatingly dumb, to get it
            # to actualy really use the IdentityFile we pass in via -i we also
            # need to tell it to ignore ssh-agent (IdentitiesOnly=true) and not
            # read in any identities from ~/.ssh/config etc (-F /dev/null),
            # because they append and it tries them in order, starting with config file
            env['GIT_SSH_COMMAND'] = " ".join([
                GIT_SSH_COMMAND,
                "-F", "/dev/null",
                "-o", "IdentitiesOnly=yes",
                "-i", self.ssh_key_file,
            ])

        command = ['git']
        if from_repo:
            command.extend(['-C', self.local_path])
        command.extend(args)

        log.info('Running %s', ' '.join(shlex.quote(w) for w in command))
        try:
            timeout_seconds = self.timeout.total_seconds() if self.timeout is not None else None
            return _run(*command, env=env, check=True, timeout=timeout_seconds)
        except subprocess.CalledProcessError as err:
            log.warning('git returned %s', err.returncode)
            log.warning('stdout: %r', err.stdout)
            log.warning('stderr: %r', err.stderr)
            raise GitError(err)


def _run(*args, env=None, check=False, timeout=None):
    with subprocess.Popen([a.encode('utf-8') for a in args], env=env, stdout=PIPE, stderr=PIPE) as process:
        try:
            stdout, stderr = process.communicate(input, timeout=timeout)
        except TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            raise TimeoutExpired(
                process.args, timeout, output=stdout, stderr=stderr,
            )
        except:
            process.kill()
            process.wait()
            raise
        retcode = process.poll()
        if check and retcode:
            raise subprocess.CalledProcessError(
                retcode, process.args, output=stdout, stderr=stderr,
            )
        return subprocess.CompletedProcess(process.args, retcode, stdout, stderr)


class GitError(Exception):
    pass
