import tempfile

from . import git


class RepoManager:

    def __init__(self, user, root_dir, ssh_key_file=None, timeout=None, reference=None):
        self._root_dir = root_dir
        self._user = user
        self._ssh_key_file = ssh_key_file
        self._repos = {}
        self._timeout = timeout
        self._reference = reference

    def repo_for_project(self, project):
        repo = self._repos.get(project.id)
        if not repo or repo.remote_url != project.ssh_url_to_repo:
            repo_url = project.ssh_url_to_repo
            local_repo_dir = tempfile.mkdtemp(dir=self._root_dir)

            repo = git.Repo(repo_url, local_repo_dir, ssh_key_file=self._ssh_key_file,
                            timeout=self._timeout, reference=self._reference)
            repo.clone()
            repo.config_user_info(
                user_email=self._user.email,
                user_name=self._user.name,
            )

            self._repos[project.id] = repo

        return repo

    def forget_repo(self, project):
        self._repos.pop(project.id, None)

    @property
    def user(self):
        return self._user

    @property
    def root_dir(self):
        return self._root_dir

    @property
    def ssh_key_file(self):
        return self._ssh_key_file
