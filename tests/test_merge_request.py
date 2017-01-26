from unittest.mock import Mock

from marge.gitlab import Api, GET, POST, PUT
from marge.merge_request import MergeRequest


class TestMergeRequest(object):
    def setup_method(self, _method):
        self.api = Mock(Api)
        self.mr = MergeRequest(project_id=1234, merge_request_id=42, api=self.api)
        self.api.call.reset_mock()

    def test_init_fetches_info(self):
        fresh = object()
        self.api.call = Mock(return_value=fresh)

        merge_request = MergeRequest(project_id=1234, merge_request_id=42, api=self.api)
        self.api.call.assert_called_once_with(GET('/projects/1234/merge_requests/42'))
        assert merge_request.info == fresh

    def test_refetch_info(self):
        fresh = object()
        self.api.call = Mock(return_value=fresh)

        self.mr.refetch_info()
        self.api.call.assert_called_once_with(GET('/projects/1234/merge_requests/42'))
        assert self.mr.info == fresh

    def test_properties(self):
        mr = self.mr
        self._load({
          'iid': 54,
          'title': 'a title',
          'assignee': {'id': 77},
          'state': 'opened',
          'sha': 'dead4g00d',
          'source_project_id': 5678,
          'target_project_id': 1234,
          'source_branch': 'useless_new_feature',
          'target_branch': 'master',
        })

        assert mr.id == 42
        assert mr.project_id == 1234
        assert mr.iid == 54
        assert mr.title == 'a title'
        assert mr.assignee_id == 77
        assert mr.state == 'opened'
        assert mr.source_branch == 'useless_new_feature'
        assert mr.target_branch == 'master'
        assert mr.sha == 'dead4g00d'
        assert mr.source_project_id == 5678
        assert mr.target_project_id == 1234

        self._load({'assignee': {}})
        assert mr.assignee_id == None

    def test_comment(self):
        self.mr.comment('blah')
        self.api.call.assert_called_once_with(POST('/projects/1234/merge_requests/42/notes', {'body': 'blah'}))

    def test_assign(self):
        self.mr.assign_to(42)
        self.api.call.assert_called_once_with(PUT('/projects/1234/merge_requests/42', {'assignee_id': 42}))

    def test_unassign(self):
        self.mr.unassign()
        self.api.call.assert_called_once_with(PUT('/projects/1234/merge_requests/42', {'assignee_id': None}))

    def test_accept(self):
        self._load({'sha': 'badc0de'})

        for b in (True, False):
            self.mr.accept(remove_branch=b)
            self.api.call.assert_called_once_with(PUT(
                '/projects/1234/merge_requests/42/merge',
                dict(
                    merge_when_build_succeeds=True,
                    should_remove_source_branch=b,
                    sha='badc0de',
                )
            ))
            self.api.call.reset_mock()

        self.mr.accept(sha='g00dc0de')
        self.api.call.assert_called_once_with(PUT(
            '/projects/1234/merge_requests/42/merge',
            dict(
                merge_when_build_succeeds=True,
                should_remove_source_branch=False,
                sha='g00dc0de',
            )
        ))

    def _load(self, json):
        old_mock = self.api.call
        self.api.call = Mock(return_value=json)
        self.mr.refetch_info()
        self.api.call.assert_called_with(GET('/projects/1234/merge_requests/42'))
        self.api.call = old_mock
