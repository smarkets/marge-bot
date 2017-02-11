from . import gitlab


GET = gitlab.GET


class Commit(gitlab.Resource):

    @classmethod
    def fetch_by_id(cls, project_id, sha, api):
        info = api.call(GET(
            '/projects/%s/repository/commits/%s' % (project_id, sha),
        ))
        return cls(api, info)

    @property
    def short_id(self):
        return self.info['short_id']

    @property
    def title(self):
        return self.info['title']

    @property
    def author_name(self):
        return self.info['author_name']

    @property
    def author_email(self):
        return self.info['author_email']

    @property
    def status(self):
        return self.info['status']
