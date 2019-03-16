from unittest.mock import Mock
import pytest

from marge.gitlab import Api, GET, Version
from marge.project import AccessLevel, Project


INFO = {
    'id': 1234,
    'path_with_namespace': 'cool/project',
    'ssh_url_to_repo': 'ssh://blah.com/cool/project.git',
    'merge_requests_enabled': True,
    'only_allow_merge_if_pipeline_succeeds': True,
    'only_allow_merge_if_all_discussions_are_resolved': False,
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


# pylint: disable=attribute-defined-outside-init,duplicate-code
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
        api.collect_all_pages = Mock(return_value=[prj1, prj2, prj3])

        project = Project.fetch_by_path('foo/bar', api)

        api.collect_all_pages.assert_called_once_with(GET('/projects'))
        assert project and project.info == prj2

    def fetch_all_mine_with_permissions(self):
        prj1, prj2 = INFO, dict(INFO, id=678)

        api = self.api
        api.collect_all_pages = Mock(return_value=[prj1, prj2])
        api.version = Mock(return_value=Version.parse("11.0.0-ee"))

        result = Project.fetch_all_mine(api)
        api.collect_all_pages.assert_called_once_with(GET(
            '/projects',
            {
                'membership': True,
                'with_merge_requests_enabled': True,
            },
        ))
        assert [prj.info for prj in result] == [prj1, prj2]
        assert all(prj.access_level == AccessLevel.developer for prj in result)

    def fetch_all_mine_with_min_access_level(self):
        prj1, prj2 = dict(INFO, permissions=NONE_ACCESS), dict(INFO, id=678, permissions=NONE_ACCESS)

        api = self.api
        api.collect_all_pages = Mock(return_value=[prj1, prj2])
        api.version = Mock(return_value=Version.parse("11.2.0-ee"))

        result = Project.fetch_all_mine(api)
        api.collect_all_pages.assert_called_once_with(GET(
            '/projects',
            {
                'membership': True,
                'with_merge_requests_enabled': True,
                "min_access_level": AccessLevel.developer.value,
            },
        ))
        assert [prj.info for prj in result] == [prj1, prj2]
        assert all(prj.info["permissions"]["marge"] for prj in result)
        assert all(prj.access_level == AccessLevel.developer for prj in result)

    def test_properties(self):
        project = Project(api=self.api, info=INFO)
        assert project.id == 1234
        assert project.path_with_namespace == 'cool/project'
        assert project.ssh_url_to_repo == 'ssh://blah.com/cool/project.git'
        assert project.merge_requests_enabled is True
        assert project.only_allow_merge_if_pipeline_succeeds is True
        assert project.only_allow_merge_if_all_discussions_are_resolved is False
        assert project.access_level == AccessLevel.developer

    def test_group_access(self):
        project = Project(api=self.api, info=dict(INFO, permissions=GROUP_ACCESS))
        bad_project = Project(api=self.api, info=dict(INFO, permissions=NONE_ACCESS))
        assert project.access_level == AccessLevel.developer
        with pytest.raises(AssertionError):
            bad_project.access_level  # pylint: disable=pointless-statement
