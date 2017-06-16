from collections import OrderedDict
from unittest.mock import ANY, call, Mock, patch

from marge.gitlab import Api, GET, POST
from marge.approvals import Approvals
import marge.user
# testing this here is more convenient
from marge.bot import _get_reviewer_names_and_emails

INFO = {
  "id": 5,
  "iid": 5,
  "project_id": 1,
  "title": "Approvals API",
  "description": "Test",
  "state": "opened",
  "created_at": "2016-06-08T00:19:52.638Z",
  "updated_at": "2016-06-08T21:20:42.470Z",
  "merge_status": "can_be_merged",
  "approvals_required": 3,
  "approvals_left": 1,
  "approved_by": [
    {
      "user": {
        "name": "Administrator",
        "username": "root",
        "id": 1,
        "state": "active",
        "avatar_url": "http://www.gravatar.com/avatar/e64c7d89f26bd1972efa854d13d7dd61?s=80\u0026d=identicon",
        "web_url": "http://localhost:3000/u/root"
      },
    },
    {
      "user": {
        "name": "Roger Ebert",
        "username": "ebert",
        "id": 2,
        "state": "active",
      }
    }
  ]
}

USERS = {
    1: {
        "name": "Administrator",
        "username": "root",
        "id": 1,
        "state": "active",
        "email": "root@localhost"
    },
    2: {
        "name": "Roger Ebert",
        "username": "ebert",
        "id": 2,
        "state": "active",
        "email": "ebert@example.com",
    }}


class TestApprovals(object):
    def setup_method(self, _method):
        self.api = Mock(Api)
        self.approvals = Approvals(api=self.api, info=INFO)

    def test_fetch_by_id(self):
        api = self.api
        api.call = Mock(return_value=INFO)

        approvals = Approvals.fetch_approvals_for_merge_request(project_id=1234, merge_request_id=5, api=api)

        api.call.assert_called_once_with(GET(
            '/projects/1234/merge_requests/5/approvals'
        ))
        assert approvals.info == INFO

    def test_properties(self):
        assert self.approvals.project_id == 1
        assert self.approvals.approvals_left == 1
        assert self.approvals.approver_usernames == ['root', 'ebert']
        assert not self.approvals.sufficient

    def test_sufficiency(self):
        good_approvals = Approvals(api=self.api, info=dict(INFO, approvals_required=1, approvals_left=0))
        assert good_approvals.sufficient

    def test_refetch_info(self):
        self.approvals.reapprove()
        self.api.call.has_calls([
            call(POST(endpoint='/projects/1/merge_requests/5/approve', args={}, extract=None), sudo=1),
            call(POST(endpoint='/projects/1/merge_requests/5/approve', args={}, extract=None), sudo=2)
        ])


    @patch('marge.user.User.fetch_by_id')
    def test_get_reviewer_names_and_emails(self, user_fetch_by_id):
        user_fetch_by_id.side_effect = lambda id, _: marge.user.User(self.api, USERS[id])
        assert _get_reviewer_names_and_emails(approvals=self.approvals, api=self.api) == [
            'Administrator <root@localhost>',
            'Roger Ebert <ebert@example.com>'
        ]
