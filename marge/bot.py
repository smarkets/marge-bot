import logging as log
import time
from datetime import datetime
from tempfile import TemporaryDirectory

from . import git
from . import gitlab
from . import merge_request as merge_request_module
from . import store
from .job import MergeJob, MergeJobOptions
from .project import AccessLevel, Project

MergeRequest = merge_request_module.MergeRequest


class Bot(object):
    def __init__(
            self,
            *,
            api,
            user,
            ssh_key_file,
            add_reviewers,
            add_tested,
            impersonate_approvers
    ):
        # There's a bug in some recent versions of Gitlab, where is_admin is
        # not set, even for admins. Use sudo (which only admins can do) as a
        # hack as work around.
        # See e.g. <https://gitlab.com/gitlab-org/gitlab-ce/issues/34325>
        if user.is_admin is None:
            try:
                user.myself(api=api, sudo=user.id)
                user._info['is_admin'] = True  # pylint: disable=protected-access
            except gitlab.Forbidden:
                pass
        if not user.is_admin:
            assert not impersonate_approvers, "{0.username} is not an admin, can't impersonate!".format(user)
            assert not add_reviewers, (
                "{0.username} is not an admin, can't lookup Reviewed-by: email addresses ".format(user)
            )

        self._ssh_key_file = ssh_key_file

        self.embargo_intervals = []

        self._api = api
        self._user = user

        self.merge_options = MergeJobOptions(
            add_tested=add_tested,
            add_reviewers=add_reviewers,
            reapprove=impersonate_approvers,
        )

    def start(self):
        with TemporaryDirectory() as root_dir:
            repo_manager = store.RepoManager(
                user=self._user, root_dir=root_dir, ssh_key_file=self._ssh_key_file,
            )
            self._run(repo_manager)

    @property
    def user(self):
        return self._user

    @property
    def api(self):
        return self._api

    def _run(self, repo_manager):
        while True:
            log.info('Finding out my current projects...')
            my_projects = Project.fetch_all_mine(self._api)

            for project in my_projects:
                project_name = project.path_with_namespace

                if project.access_level.value < AccessLevel.reporter.value:
                    log.warning("Don't have enough permissions to browse merge requests in %s!", project_name)
                    continue

                log.info('Fetching merge requests assigned to me in %s...', project_name)
                my_merge_requests = MergeRequest.fetch_all_open_for_user(
                    project_id=project.id,
                    user_id=self._user.id,
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

                    job = MergeJob(
                        bot=self,
                        project=project, merge_request=merge_request, repo=repo,
                    )
                    job.execute()
                else:
                    log.info('Nothing to merge at this point...')

            time_to_sleep_in_secs = 60
            log.info('Sleeping for %s seconds...', time_to_sleep_in_secs)
            time.sleep(time_to_sleep_in_secs)

    def during_merge_embargo(self):
        now = datetime.utcnow()
        return any(interval.covers(now) for interval in self.embargo_intervals)
