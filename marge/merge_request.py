from . import gitlab


GET, POST, PUT = gitlab.GET, gitlab.POST, gitlab.PUT


class MergeRequest(gitlab.Resource):

    @classmethod
    def fetch_by_iid(cls, project_id, merge_request_iid, api):
        merge_request = cls(api, {'iid': merge_request_iid, 'project_id': project_id})
        merge_request.refetch_info()
        return merge_request

    @classmethod
    def fetch_all_open_for_user(cls, project_id, user_id, api):
        all_merge_request_infos = api.collect_all_pages(GET(
            '/projects/{project_id}/merge_requests'.format(project_id=project_id),
            {'state': 'opened', 'order_by': 'created_at', 'sort': 'asc'},
        ))
        my_merge_request_infos = [
            mri for mri in all_merge_request_infos
            if (mri['assignee'] or {}).get('id') == user_id
        ]

        return [cls(api, merge_request_info) for merge_request_info in my_merge_request_infos]

    @property
    def project_id(self):
        return self.info['project_id']

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
    def author_id(self):
        return self.info['author'].get('id')

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

    @property
    def work_in_progress(self):
        return self.info['work_in_progress']

    @property
    def approved_by(self):
        return self.info['approved_by']

    @property
    def web_url(self):
        return self.info['web_url']

    def refetch_info(self):
        self._info = self._api.call(GET('/projects/%s/merge_requests/%s' % (self.project_id, self.iid)))

    def comment(self, message):
        return self._api.call(POST(
            '/projects/%s/merge_requests/%s/notes' % (self.project_id, self.iid),
            {'body': message},
        ))

    def accept(self, remove_branch=False, sha=None):
        return self._api.call(PUT(
            '/projects/%s/merge_requests/%s/merge' % (self.project_id, self.iid),
            dict(
                should_remove_source_branch=remove_branch,
                merge_when_pipeline_succeeds=True,
                sha=sha or self.sha,  # if provided, ensures what is merged is what we want (or fails)
            ),
        ))

    def assign_to(self, user_id):
        return self._api.call(PUT(
            '/projects/%s/merge_requests/%s' % (self.project_id, self.iid),
            {'assignee_id': user_id},
        ))

    def unassign(self):
        return self.assign_to(None)
