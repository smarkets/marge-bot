import logging as log
import shlex
import os
import subprocess
from collections import namedtuple
from subprocess import PIPE

TIMEOUT_IN_SECS = 60

class Repo(namedtuple('Repo', 'remote_url local_path ssh_key_file')):
    def clone(self):
        self.git('clone', '--origin=origin', self.remote_url, self.local_path, from_repo=False)

    def rebase(self, branch, new_base):
        assert branch != new_base, branch

        success = False

        self.git('fetch', 'origin')
        self.git('checkout', branch)

        try:
            self.git('rebase', 'origin/%s' % new_base)
            success = True
        except GitError as e:
            self.git('rebase', '--abort')

        return success

    def remove_branch(self, branch):
        assert branch != 'master'
        self.git('checkout', 'master')
        self.git('branch', '-D', branch)

    def push_force(self, branch):
        self.git('checkout', branch)

        self.git('diff-index', '--quiet', 'HEAD')  # check it is not dirty

        untracked_files = self.git('ls-files', '--others').stdout  # check no untracked files
        assert len(untracked_files) == 0, untracked_files

        self.git('push', '--force', 'origin', branch)

    def get_head_commit_hash(self):
        result = self.git('rev-parse', 'HEAD')
        return str(result.stdout, encoding='ascii').strip()

    def git(self, *args, from_repo=True):
        env = None
        if self.ssh_key_file:
            env = os.environ.copy()
            env['GIT_SSH_COMMAND'] = "ssh -i %s" % self.ssh_key_file

        command = ['git']
        if from_repo:
            command.extend(['-C', self.local_path])
        command.extend(args)

        log.info('Running %s', ' '.join(shlex.quote(w) for w in command))
        try:
            return _run(*command, env=env, check=True, timeout=TIMEOUT_IN_SECS)
        except subprocess.CalledProcessError as e:
            log.warning('git returned %s', e.returncode)
            raise GitError(e)


def _run(*args, env=None, check=False, timeout=None):
    with subprocess.Popen(args, env=env, stdout=PIPE, stderr=PIPE) as process:
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
