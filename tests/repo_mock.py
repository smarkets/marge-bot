import contextlib
import logging as log
import os
import subprocess
import tempfile

from marge.git import Repo
from marge.store import RepoManager
from marge.user import User


class MockRepo(Repo):
    @classmethod
    def init(cls, local_path):
        self = cls(remote_url=None, local_path=local_path, ssh_key_file=None)
        self.git('init', self.local_path, from_repo=False)
        self.config_user_info('Irrelevant', 'someone@invalid')
        return self

    def git_url(self):
        return self.local_path + '/.git'

    @staticmethod
    def _canonical_contents(full_path, contents):
        if type(contents) is str:
            return contents.encode('utf-8')
        elif type(contents) in (bytes, None):
            return contents
        with open(full_path, 'rb') as ih:
            return contents(ih.read())

    def _add_or_remove_file(self, path, contents):
        full_path = os.path.join(self.local_path, path)
        contents = self._canonical_contents(full_path, contents)
        if contents is None:
            self.git('rm', '--', path)
        else:
            dir = os.path.dirname(full_path)
            if not os.path.exists(dir):
                subprocess.check_call(['mkdir', '-P', '--', dir])

            with open(full_path, 'wb') as oh:
                oh.write(contents)
            self.git('add', '--', path)

    def add_commit(self, files, commit_msg, author='C. Ommitor <commitor@invalid>', branch=None):
        """Create a commit, adding, deleting or modifying `files` on `branch`, default master.

        Files is a Dict[str, bytes | Function[bytes, bytes] | None ] mapping
        filenames to contents or a function to modify them. None, or the
        function returning None means the file will be removed.

        """
        for rel_path, contents in files.items():
            self._add_or_remove_file(rel_path, contents)
        if branch:
            create = not self.git('rev-parse', '--verify', branch, check=False).returncode == 0
            self.checkout(branch, create=create)
        self.git('commit', '--author', author, '-m', commit_msg, '--', *files)
        self.checkout('master')


class MockRepoManager(RepoManager):

    #    @contextlib.contextmanager
    @classmethod
    def store(cls, remotes=0):
        with tempfile.TemporaryDirectory() as repos_dir:
            log.info('Repos root: %s', repos_dir)
            marge = User(None, {'name': 'pseudo-marge-bot', 'email': 'pseudo-marge-bot@invalid'})
            store = cls(marge, repos_dir)
            ans = [store] + [MockRepo.init(tempfile.mkdtemp(dir=repos_dir)) for i in range(remotes)]
            yield tuple(ans)


subprocess.check_call('rm -rf /tmp/foobar'.split())
mr = MockRepo.init('/tmp/foobar')
mr.add_commit({'README.md': b'So exciting project!\n'}, 'First commit')
mr.add_commit(
    {'README.md': lambda s: s + b'\ngot even better'},
    'Second Commit: PR 1; just merge',
    branch='clean-pr',
)
mr.add_commit(
    {'newfile.txt': b'Turning over a new leaf.'},
    'Third Commit: PR 2 start',
    branch='pr-that-will-need-rebasing',
)
# mr.add_commit(
#     {'newfile.txt': lambda s: s + b'\nJust a bit more text for second commit.'},
#     'Fourth Commit: PR 2 cont; rebase',
#     branch='pr-that-will-need-rebasing',
# )
# mr.add_commit(
#     {'newfile.txt': lambda s: s + b'\nAgain!'},
#     'Fifth Commit: PR 2 end; rebase',
#     branch='pr-that-will-need-rebasing',
# )
# mr.add_commit(
#     {'README': lambda s: b'Just add some intro\n.' + s},
#     'Sixth Commit: PR 3; rebase, clean merge',
#     branch='pr-that-will-need-rebasing',
#     )
# mr.add_commit(
#     {'README': lambda s: s + b'This is gonna conflicts'},
#     'Seventh Commit: PR 4; conflict',
#     branch='pr-that-will-need-rebasing',
# )
# mr.add_commit(
#     {'one-more-file.txt': lambda s: s + b'This is gonna conflicts'},
#     'Eigth Commit: PR 4; conflict',
#     branch='pr-that-will-need-rebasing',
# )
# mr.add_commit(
#     {'one-more-file.txt': lambda s: s + b'This is gonna conflicts'},
#     'Ninth Commit: PR 4; conflict',
#     branch='pr-that-will-need-rebasing',
# )
# mr.add_commit(
#     {'two-more-file.txt': 'Behold, a file!'},
#     'Tenth Commit: PR 4; conflict',
#     branch='pr-that-will-need-rebasing',
# )
# process above
#mr.add_commit({'README': lambda s: None}, branch='master', 'Sneaky commit, moving master')
