from unittest.mock import ANY, Mock

from marge.gitlab import Api, GET
from marge.commit import Commit


INFO = {
  "id": "6104942438c14ec7bd21c6cd5bd995272b3faff6",
  "short_id": "6104942438c",
  "title": "Sanitize for network graph",
  "author_name": "randx",
  "author_email": "dmitriy.zaporozhets@gmail.com",
  "committer_name": "Dmitriy",
  "committer_email": "dmitriy.zaporozhets@gmail.com",
  "created_at": "2012-09-20T09:06:12+03:00",
  "message": "Sanitize for network graph",
  "committed_date": "2012-09-20T09:06:12+03:00",
  "authored_date": "2012-09-20T09:06:12+03:00",
  "parent_ids": [
    "ae1d9fb46aa2b07ee9836d49862ec4e2c46fbbba"
  ],
  "stats": {
    "additions": 15,
    "deletions": 10,
    "total": 25
  },
  "status": "running"
}


class TestProject(object):
    def setup_method(self, _method):
        self.api = Mock(Api)

    def test_fetch_by_id(self):
        api = self.api
        api.call = Mock(return_value=INFO)

        commit = Commit.fetch_by_id(project_id=1234, sha=INFO['id'], api=api)

        api.call.assert_called_once_with(GET(
            '/projects/1234/repository/commits/6104942438c14ec7bd21c6cd5bd995272b3faff6'
        ))
        assert commit.info == INFO

    def test_properties(self):
        commit = Commit(api=self.api, info=INFO)
        assert commit.id == "6104942438c14ec7bd21c6cd5bd995272b3faff6"
        assert commit.short_id == "6104942438c"
        assert commit.title == "Sanitize for network graph"
        assert commit.author_name == "randx"
        assert commit.author_email == "dmitriy.zaporozhets@gmail.com"
        assert commit.status == "running"
