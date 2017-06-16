from unittest.mock import ANY, Mock

from marge.gitlab import Api, GET
from marge.user import User


INFO = {
    'id': 1234,
    'username': 'john_smith',
    'name': 'John Smith',
    'state': 'active',
}


class TestProject(object):
    def setup_method(self, _method):
        self.api = Mock(Api)

    def test_fetch_myself(self):
        user = User.myself(api=self.api)
        self.api.call.assert_called_once_with(GET('/user'), sudo=None)

    def test_fetch_by_id(self):
        api = self.api
        api.call = Mock(return_value=INFO)

        user = User.fetch_by_id(user_id=1234, api=api)

        api.call.assert_called_once_with(GET('/users/1234'))
        assert user.info == INFO

    def test_fetch_by_username_exists(self):
        api = self.api
        api.call = Mock(return_value = INFO)

        user = User.fetch_by_username('john_smith', api)

        api.call.assert_called_once_with(GET('/users', {'username': 'john_smith'}, ANY))
        assert user and user.info == INFO

    def test_properties(self):
        user = User(api=self.api, info=INFO)
        assert user.id == 1234
        assert user.username == 'john_smith'
        assert user.name == 'John Smith'
        assert user.state == 'active'
