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
    def only_allow_merge_if_build_succeeds(self):
        return self.info['only_allow_merge_if_build_succeeds']
