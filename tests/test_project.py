from unittest.mock import Mock

from marge.gitlab import Api, GET
from marge.project import AccessLevel, Project


INFO = {
    'id': 1234,
    'path_with_namespace': 'cool/project',
    'ssh_url_to_repo': 'ssh://blah.com/cool/project.git',
    'merge_requests_enabled': True,
    'only_allow_merge_if_pipeline_succeeds': True,
    'permissions': {
        'project_access': {
            'access_level': AccessLevel.developer.value,
        },
        'group_access': {
            'access_level': AccessLevel.developer.value,
        }
    }
}

GROUP_ACCESS = {
    'project_access': None,
    'group_access': {
        'access_level': AccessLevel.developer.value,
    }
}

NONE_ACCESS = {
    'project_access': None,
    'group_access': None
}


class TestProject(object):
    def setup_method(self, _method):
        self.api = Mock(Api)

    def test_fetch_by_id(self):
        api = self.api
        api.call = Mock(return_value=INFO)

        project = Project.fetch_by_id(project_id=1234, api=api)

        api.call.assert_called_once_with(GET('/projects/1234'))
        assert project.info == INFO

    def test_fetch_by_path_exists(self):
        api = self.api
        prj1 = INFO
        prj2 = dict(INFO, id=1235, path_with_namespace='foo/bar')
        prj3 = dict(INFO, id=1240, path_with_namespace='foo/foo')
        api.collect_all_pages = Mock(return_value = [prj1, prj2, prj3])

        project = Project.fetch_by_path('foo/bar', api)

        api.collect_all_pages.assert_called_once_with(GET('/projects'))
        assert project and project.info == prj2

    def test_fetch_all_mine(self):
        prj1, prj2 = INFO, dict(INFO, id=678)

        api = self.api
        api.collect_all_pages = Mock(return_value = [prj1, prj2])

        result = Project.fetch_all_mine(api)
        api.collect_all_pages.assert_called_once_with(GET(
            '/projects',
            {'membership': True, 'with_merge_requests_enabled': True},
        ))
        assert [prj.info for prj in result] == [prj1, prj2]

    def test_properties(self):
        project = Project(api=self.api, info=INFO)
        assert project.id == 1234
        assert project.path_with_namespace == 'cool/project'
        assert project.ssh_url_to_repo == 'ssh://blah.com/cool/project.git'
        assert project.merge_requests_enabled == True
        assert project.only_allow_merge_if_pipeline_succeeds == True
        assert project.access_level == AccessLevel.developer

    def test_group_access(self):
        project = Project(api=self.api, info=dict(INFO, permissions=GROUP_ACCESS))
        project2 = Project(api=self.api, info=dict(INFO, permissions=NONE_ACCESS))
        assert project.access_level == AccessLevel.developer
        assert project2.access_level == None
