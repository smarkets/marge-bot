from unittest.mock import Mock

from marge.gitlab import Api, GET, POST, PUT, Version
from marge.merge_request import MergeRequest

_MARGE_ID = 77

INFO = {
    'id': 42,
    'iid': 54,
    'title': 'a title',
    'project_id': 1234,
    'assignee': {'id': _MARGE_ID},
    'author': {'id': 88},
    'state': 'opened',
    'sha': 'dead4g00d',
    'source_project_id': 5678,
    'target_project_id': 1234,
    'source_branch': 'useless_new_feature',
    'target_branch': 'master',
    'work_in_progress': False,
}


# pylint: disable=attribute-defined-outside-init
class TestMergeRequest(object):

    def setup_method(self, _method):
        self.api = Mock(Api)
        self.api.version = Mock(return_value=Version.parse('9.2.3-ee'))
        self.merge_request = MergeRequest(api=self.api, info=INFO)

    def test_fetch_by_iid(self):
        api = self.api
        api.call = Mock(return_value=INFO)

        merge_request = MergeRequest.fetch_by_iid(project_id=1234, merge_request_iid=54, api=api)

        api.call.assert_called_once_with(GET('/projects/1234/merge_requests/54'))
        assert merge_request.info == INFO

    def test_refetch_info(self):
        new_info = dict(INFO, state='closed')
        self.api.call = Mock(return_value=new_info)

        self.merge_request.refetch_info()
        self.api.call.assert_called_once_with(GET('/projects/1234/merge_requests/54'))
        assert self.merge_request.info == new_info

    def test_properties(self):
        assert self.merge_request.id == 42
        assert self.merge_request.project_id == 1234
        assert self.merge_request.iid == 54
        assert self.merge_request.title == 'a title'
        assert self.merge_request.assignee_id == 77
        assert self.merge_request.author_id == 88
        assert self.merge_request.state == 'opened'
        assert self.merge_request.source_branch == 'useless_new_feature'
        assert self.merge_request.target_branch == 'master'
        assert self.merge_request.sha == 'dead4g00d'
        assert self.merge_request.source_project_id == 5678
        assert self.merge_request.target_project_id == 1234
        assert self.merge_request.work_in_progress is False

        self._load({'assignee': {}})
        assert self.merge_request.assignee_id is None

    def test_comment(self):
        self.merge_request.comment('blah')
        self.api.call.assert_called_once_with(
            POST(
                '/projects/1234/merge_requests/54/notes',
                {'body': 'blah'},
            ),
        )

    def test_assign(self):
        self.merge_request.assign_to(42)
        self.api.call.assert_called_once_with(PUT('/projects/1234/merge_requests/54', {'assignee_id': 42}))

    def test_unassign(self):
        self.merge_request.unassign()
        self.api.call.assert_called_once_with(PUT('/projects/1234/merge_requests/54', {'assignee_id': None}))

    def test_accept(self):
        self._load(dict(INFO, sha='badc0de'))

        for boolean in (True, False):
            self.merge_request.accept(remove_branch=boolean)
            self.api.call.assert_called_once_with(PUT(
                '/projects/1234/merge_requests/54/merge',
                dict(
                    merge_when_pipeline_succeeds=True,
                    should_remove_source_branch=boolean,
                    sha='badc0de',
                )
            ))
            self.api.call.reset_mock()

        self.merge_request.accept(sha='g00dc0de')
        self.api.call.assert_called_once_with(PUT(
            '/projects/1234/merge_requests/54/merge',
            dict(
                merge_when_pipeline_succeeds=True,
                should_remove_source_branch=False,
                sha='g00dc0de',
            )
        ))

    def test_fetch_all_opened_for_me(self):
        api = self.api
        mr1, mr_not_me, mr2 = INFO, dict(INFO, assignee={'id': _MARGE_ID+1}, id=679), dict(INFO, id=678)
        api.collect_all_pages = Mock(return_value=[mr1, mr_not_me, mr2])
        result = MergeRequest.fetch_all_open_for_user(
            1234, user_id=_MARGE_ID, api=api, merge_order='created_at'
        )
        api.collect_all_pages.assert_called_once_with(GET(
            '/projects/1234/merge_requests',
            {'state': 'opened', 'order_by': 'created_at', 'sort': 'asc'},
        ))
        assert [mr.info for mr in result] == [mr1, mr2]

    def _load(self, json):
        old_mock = self.api.call
        self.api.call = Mock(return_value=json)
        self.merge_request.refetch_info()
        self.api.call.assert_called_with(GET('/projects/1234/merge_requests/54'))
        self.api.call = old_mock
