from . import gitlab


GET = gitlab.GET


class Member(gitlab.Resource):

    @classmethod
    def fetch_by_id(cls, project_id, member_id, api):
        info = api.call(GET('/projects/%s/members/all/%s' % (project_id, member_id)))
        return cls(api, info)

    @property
    def access_level(self):
        return self.info['access_level']
