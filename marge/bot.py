import logging as log
import time
from collections import namedtuple
from tempfile import TemporaryDirectory

from . import git
from . import job
from . import merge_request as merge_request_module
from . import store
from .project import AccessLevel, Project

MergeRequest = merge_request_module.MergeRequest


class Bot(object):
    def __init__(self, *, api, config):
        self._api = api
        self._config = config

        user = config.user
        opts = config.merge_opts

        if not user.is_admin:
            assert not opts.reapprove, (
                "{0.username} is not an admin, can't impersonate!".format(user)
            )
            assert not opts.add_reviewers, (
                "{0.username} is not an admin, can't lookup Reviewed-by: email addresses ".format(user)
            )

    def start(self):
        with TemporaryDirectory() as root_dir:
            repo_manager = store.RepoManager(
                user=self.user, root_dir=root_dir, ssh_key_file=self._config.ssh_key_file,
            )
            self._run(repo_manager)

    @property
    def user(self):
        return self._config.user

    @property
    def api(self):
        return self._api

    def _run(self, repo_manager):
        while True:
            log.info('Finding out my current projects...')
            my_projects = Project.fetch_all_mine(self._api)
            project_regexp = self._config.project_regexp
            filtered_projects = [p for p in my_projects if project_regexp.match(p.path_with_namespace)]
            filtered_out = set(my_projects) - set(filtered_projects)
            if filtered_out:
                log.debug(
                    'Projects that match project_regexp: %s',
                    [p.path_with_namespace for p in filtered_projects]
                )
                log.debug(
                    'Projects that do not match project_regexp: %s',
                    [p.path_with_namespace for p in filtered_out]
                )
            for project in filtered_projects:
                project_name = project.path_with_namespace

                if project.access_level.value < AccessLevel.reporter.value:
                    log.warning("Don't have enough permissions to browse merge requests in %s!", project_name)
                    continue

                log.info('Fetching merge requests assigned to me in %s...', project_name)
                my_merge_requests = MergeRequest.fetch_all_open_for_user(
                    project_id=project.id,
                    user_id=self.user.id,
                    api=self._api
                )

                if my_merge_requests:
                    log.info('Got %s requests to merge; will try to merge the oldest', len(my_merge_requests))
                    merge_request = my_merge_requests[0]
                    try:
                        repo = repo_manager.repo_for_project(project)
                    except git.GitError:
                        log.exception("Couldn't initialize repository for project!")
                        raise

                    merge_job = job.MergeJob(
                        api=self._api, user=self.user,
                        project=project, merge_request=merge_request, repo=repo,
                        options=self._config.merge_opts,
                    )
                    merge_job.execute()
                else:
                    log.info('Nothing to merge at this point...')

            time_to_sleep_in_secs = 60
            log.info('Sleeping for %s seconds...', time_to_sleep_in_secs)
            time.sleep(time_to_sleep_in_secs)


class BotConfig(namedtuple('BotConfig', 'user ssh_key_file project_regexp merge_opts')):
    pass

MergeJobOptions = job.MergeJobOptions
