from . import gitlab


GET, POST, PUT = gitlab.GET, gitlab.POST, gitlab.PUT


class MergeRequest(object):
    def __init__(self, api, info):
        self._api = api
        self._info = info

    @classmethod
    def fetch_by_id(cls, project_id, merge_request_id, api):
        merge_request = cls(api, {'id': merge_request_id, 'project_id': project_id})
        merge_request.refetch_info()
        return merge_request

    @classmethod
    def fetch_all_opened(cls, project_id, api):
        merge_requests = api.collect_all_pages(GET(
            '/projects/%s/merge_requests' % project_id,
            {'state': 'opened', 'order_by': 'created_at', 'sort': 'asc'},
        ))

        return [cls(api, merge_request_info) for merge_request_info in merge_requests]

    @property
    def id(self):
        return self._info['id']

    @property
    def project_id(self):
        return self._info['project_id']

    @property
    def info(self):
        return self._info

    @property
    def iid(self):
        return self.info['iid']

    @property
    def title(self):
        return self.info['title']

    @property
    def state(self):
        return self.info['state']

    @property
    def assignee_id(self):
        assignee = self.info['assignee'] or {}
        return assignee.get('id')

    @property
    def source_branch(self):
        return self.info['source_branch']

    @property
    def target_branch(self):
        return self.info['target_branch']

    @property
    def sha(self):
        return self.info['sha']

    @property
    def source_project_id(self):
        return self.info['source_project_id']

    @property
    def target_project_id(self):
        return self.info['target_project_id']


    def refetch_info(self):
        self._info = self._api.call(GET('/projects/%s/merge_requests/%s' % (self.project_id, self.id)))

    def comment(self, message):
        return self._api.call(POST(
            '/projects/%s/merge_requests/%s/notes' % (self.project_id, self.id),
            {'body': message},
        ))

    def accept(self, remove_branch=False, sha=None):
        return self._api.call(PUT(
            '/projects/%s/merge_requests/%s/merge' % (self.project_id, self.id),
            dict(
                should_remove_source_branch=remove_branch,
                merge_when_build_succeeds=True,
                sha=sha or self.sha,  # if provided, ensures what is merged is what we want (or fails)
            ),
        ))

    def assign_to(self, user_id):
        return self._api.call(PUT(
            '/projects/%s/merge_requests/%s' % (self.project_id, self.id),
            {'assignee_id': user_id},
        ))

    def unassign(self):
        return self.assign_to(None)
