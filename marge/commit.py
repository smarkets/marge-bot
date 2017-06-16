import re

from . import gitlab


GET = gitlab.GET


class Commit(gitlab.Resource):

    @classmethod
    def fetch_by_id(cls, project_id, sha, api):
        info = api.call(GET(
            '/projects/{project_id}/repository/commits/{sha}'.format(
                project_id=project_id,
                sha=sha,
            ),
        ))
        return cls(api, info)

    @classmethod
    def last_on_branch(cls, project_id, branch, api):
        info = api.call(GET(
            '/projects/{project_id}/repository/branches/{branch}'.format(
                project_id=project_id,
                branch=branch,
            ),
        ))['commit']
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

    @property
    def reviewers(self):
        return re.findall(r'^Reviewed-by: ([^\n]+)$', self.info['message'], re.MULTILINE)

    @property
    def testers(self):
        return re.findall(r'^Tested-by: ([^\n]+)$', self.info['message'], re.MULTILINE)
