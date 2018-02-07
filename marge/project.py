import logging as log
from enum import Enum, unique
from functools import partial

from . import gitlab


GET = gitlab.GET


class Project(gitlab.Resource):

    @classmethod
    def fetch_by_id(cls, project_id, api):
        info = api.call(GET('/projects/%s' % project_id))
        return cls(api, info)

    @classmethod
    def fetch_by_path(cls, project_path, api):
        def filter_by_path_with_namespace(projects):
            return [p for p in projects if p['path_with_namespace'] == project_path]

        make_project = partial(cls, api)

        all_projects = api.collect_all_pages(GET('/projects'))
        return gitlab.from_singleton_list(make_project)(filter_by_path_with_namespace(all_projects))

    @classmethod
    def fetch_all_mine(cls, api):
        projects_info = api.collect_all_pages(GET(
            '/projects',
            {'membership': True, 'with_merge_requests_enabled': True},
        ))

        def project_seems_ok(project_info):
            # A bug in at least GitLab 9.3.5 would make GitLab not report permissions after
            # moving subgroups. See for full story #19.
            permissions = project_info['permissions']
            permissions_ok = bool(permissions['project_access'] or permissions['group_access'])
            if not permissions_ok:
                project_name = project_info['path_with_namespace']
                log.warning('Ignoring project %s since GitLab provided no user permissions', project_name)

            return permissions_ok

        return [cls(api, project_info) for project_info in projects_info if project_seems_ok(project_info)]

    @property
    def path_with_namespace(self):
        return self.info['path_with_namespace']

    @property
    def ssh_url_to_repo(self):
        return self.info['ssh_url_to_repo']

    @property
    def merge_requests_enabled(self):
        return self.info['merge_requests_enabled']

    @property
    def only_allow_merge_if_pipeline_succeeds(self):
        return self.info['only_allow_merge_if_pipeline_succeeds']

    @property
    def approvals_required(self):
        return self.info['approvals_before_merge']

    @property
    def access_level(self):
        permissions = self.info['permissions']
        effective_access = permissions['project_access'] or permissions['group_access']
        assert effective_access is not None, "GitLab failed to provide user permissions on project"
        return AccessLevel(effective_access['access_level'])


@unique
class AccessLevel(Enum):
    # See https://docs.gitlab.com/ce/api/access_requests.html
    guest = 10
    reporter = 20
    developer = 30
    master = 40
    owner = 50
