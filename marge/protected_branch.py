import sys
from . import gitlab


GET = gitlab.GET


class ProtectedBranch(gitlab.Resource):

    @classmethod
    def fetch_by_name(cls, project_id, branch_name, api):
        info = api.call(GET('/projects/%s/protected_branches/%s' % (project_id, branch_name)))
        return cls(api, info)

    @property
    def merge_min_access_level(self):
        min_access_level = 60 # instance admin
        for level in self.info['merge_access_levels']:
            if level['access_level'] < min_access_level:
                min_access_level = level['access_level']
        return min_access_level
