import logging as log
from collections import defaultdict
from datetime import timedelta
import functools
import shlex

import marge.git as git


class RepoMock(git.Repo):

    @classmethod
    def init_for_merge_request(cls, merge_request, initial_target_sha, project, forked_project=None):
        assert bool(forked_project) == (
            merge_request.source_project_id != merge_request.target_project_id
        )

        target_url = project.ssh_url_to_repo
        source_url = forked_project.ssh_url_to_repo if forked_project else target_url

        remote_repos = defaultdict(GitRepoModel)
        remote_repos[source_url].set_ref(merge_request.source_branch, merge_request.sha)
        remote_repos[target_url].set_ref(merge_request.target_branch, initial_target_sha)

        result = cls(
            remote_url=target_url,
            local_path='/tmp/blah',
            ssh_key_file='/home/homer/.ssh/id_rsa',
            timeout=timedelta(seconds=1000000),
            reference='the_reference',
        )

        # pylint: disable=attribute-defined-outside-init
        result.mock_impl = GitModel(origin=target_url, remote_repos=remote_repos)
        return result

    def git(self, *args, from_repo=True):
        command = args[0]
        command_args = args[1:]

        log.info('Run: git %r %s', command, ' '.join(map(repr, command_args)))
        assert from_repo == (command != 'clone')

        command_impl_name = command.replace('-', '_')
        command_impl = getattr(self.mock_impl, command_impl_name, None)
        assert command_impl, ('git: Unexpected command %s' % command)
        try:
            result = command_impl(*command_args)
        except Exception:
            log.warning('Failed to simulate: git %r %s', command, command_args)
            raise
        else:
            return self._pretend_result_comes_from_popen(result)

    @staticmethod
    def _pretend_result_comes_from_popen(result):
        result_bytes = ('' if result is None else str(result)).encode('ascii')
        return stub(stdout=result_bytes)


class stub:  # pylint: disable=invalid-name,too-few-public-methods
    def __init__(self, **kwargs):
        self.__dict__ = kwargs


class GitRepoModel:
    def __init__(self, copy_of=None):
        # pylint: disable=protected-access
        self._refs = dict(copy_of._refs) if copy_of else {}

    def set_ref(self, ref, commit):
        self._refs[ref] = commit

    def get_ref(self, ref):
        return self._refs[ref]

    def has_ref(self, ref):
        return ref in self._refs

    def del_ref(self, ref):
        self._refs.pop(ref, None)

    def __repr__(self):
        return "<%s: %s>" % (type(self), self._refs)


class GitModel:
    def __init__(self, origin, remote_repos):
        assert origin in remote_repos

        self.remote_repos = remote_repos
        self._local_repo = GitRepoModel()
        self._remotes = dict(origin=origin)
        self._remote_refs = {}
        self._branch = None
        self.on_push_callbacks = []

    @property
    def _head(self):
        return self._local_repo.get_ref(self._branch)

    def remote(self, *args):
        action = args[0]
        if action == 'rm':
            _, remote = args
            try:
                self._remotes.pop(remote)
            except KeyError:
                raise git.GitError('No such remote: %s' % remote)

        elif action == 'add':
            _, remote, url = args
            self._remotes[remote] = url
        else:
            assert False, args

    def fetch(self, *args):
        _, remote_name = args
        assert args == ('--prune', remote_name)
        remote_url = self._remotes[remote_name]
        remote_repo = self.remote_repos[remote_url]
        self._remote_refs[remote_name] = GitRepoModel(copy_of=remote_repo)

    def checkout(self, *args):
        if args[0] == '-B':  # -B == create if it doesn't exist
            _, branch, start_point, _ = args
            assert args == ('-B', branch, start_point, '--')
            assert start_point == '' or '/' in start_point  # '' when "local"

            # create if it doesn't exist
            if not self._local_repo.has_ref(branch):
                if start_point:
                    remote_name, remote_branch = start_point.split('/')
                    assert remote_branch == branch

                    remote_url = self._remotes[remote_name]
                    remote_repo = self.remote_repos[remote_url]
                    commit = remote_repo.get_ref(branch)
                    self._local_repo.set_ref(branch, commit)
                else:
                    self._local_repo.set_ref(branch, self._head)
        else:
            branch, _ = args
            assert args == (branch, '--')
            assert self._local_repo.has_ref(branch)

        # checkout
        self._branch = branch

    def branch(self, *args):
        if args[0] == "-D":
            _, branch = args
            assert self._branch != branch
            self._local_repo.del_ref(branch)
        else:
            assert False

    def rev_parse(self, arg):
        if arg == 'HEAD':
            return self._head

        remote, branch = arg.split('/')
        return self._remote_refs[remote].get_ref(branch)

    def rebase(self, arg):
        remote, branch = arg.split('/')
        new_base = self._remote_refs[remote].get_ref(branch)
        if new_base != self._head:
            new_sha = 'rebase(%s onto %s)' % (self._head, new_base)
            self._local_repo.set_ref(self._branch, new_sha)

    def merge(self, arg):
        remote, branch = arg.split('/')

        other_ref = self._remote_refs[remote].get_ref(branch)
        if other_ref != self._head:
            new_sha = 'merge(%s with %s)' % (self._head, other_ref)
            self._local_repo.set_ref(self._branch, new_sha)

    def push(self, *args):
        force_flag, skip_1, skip_2, remote_name, refspec = args

        assert force_flag in ('', '--force')
        assert skip_1 in ('', '-o')
        assert skip_2 in ('', 'ci.skip')

        branch, remote_branch = refspec.split(':')
        remote_url = self._remotes[remote_name]
        remote_repo = self.remote_repos[remote_url]

        old_sha = remote_repo.get_ref(remote_branch)
        new_sha = self._local_repo.get_ref(branch)

        if force_flag:
            remote_repo.set_ref(remote_branch, new_sha)
        else:
            expected_remote_sha = self._remote_refs[remote_name].get_ref(remote_branch)
            if old_sha != expected_remote_sha:
                raise git.GitError("conflict: can't push")
            remote_repo.set_ref(remote_branch, new_sha)

        for callback in self.on_push_callbacks:
            callback(
                remote_url=remote_url,
                remote_branch=remote_branch,
                old_sha=old_sha,
                new_sha=new_sha,
            )

    def config(self, *args):
        assert len(args) == 2 and args[0] == '--get'
        _, remote, _ = elems = args[1].split('.')
        assert elems == ['remote', remote, 'url'], elems
        return self._remotes[remote]

    def diff_index(self, *args):
        assert args == ('--quiet', 'HEAD')
        # we don't model dirty index

    def ls_files(self, *args):
        assert args == ('--others',)
        # we don't model untracked files

    def filter_branch(self, *args):
        _, _, filter_cmd, commit_range = args
        assert args == ('--force', '--msg-filter', filter_cmd, commit_range)

        trailers_var, python, script_path = shlex.split(filter_cmd)
        _, trailers_str = trailers_var.split('=')

        assert trailers_var == "TRAILERS=%s" % trailers_str
        assert python == "python3"
        assert script_path.endswith("marge/trailerfilter.py")

        trailers = list(sorted(set(line.split(':')[0] for line in trailers_str.split('\n'))))
        assert trailers

        new_sha = functools.reduce(
            lambda x, f: "add-%s(%s)" % (f, x),
            [trailer.lower() for trailer in trailers],
            self._head
        )
        self._local_repo.set_ref(self._branch, new_sha)
        return new_sha
