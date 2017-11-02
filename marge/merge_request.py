import sys

from . import gitlab
from .approvals import Approvals


GET, POST, PUT = gitlab.GET, gitlab.POST, gitlab.PUT

# create an unique object for default params in a reloadable fashion
NIL = getattr(sys.modules.get('marge.merge_request'), 'NIL', object())

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
    def description(self):
        return self.info['description']

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
    def squash(self):
        return self.info.get('squash', False)  # missing means auto-squash not supported

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
        self._info = self._api.call(GET('/projects/{0.project_id}/merge_requests/{0.iid}'.format(self)))

    def comment(self, message):
        if self._api.version().release >= (9, 2, 2):
            notes_url = '/projects/{0.project_id}/merge_requests/{0.iid}/notes'.format(self)
        else:
            # gitlab botched the v4 api before 9.2.2
            notes_url = '/projects/{0.project_id}/merge_requests/{0.id}/notes'.format(self)

        return self._api.call(POST(notes_url, {'body': message}))

    def update(self, *, assignee_id=NIL, title=NIL, description=NIL):
        params = {}
        if assignee_id is not NIL:
            params['assignee_id'] = assignee_id
        if title is not NIL:
            params['title'] = title
        if description is not NIL:
            params['description'] = description

        ans = self._api.call(PUT(
            '/projects/{0.project_id}/merge_requests/{0.iid}'.format(self),
            params,
        ))
        # FIXME(alexander)
        self._info = dict(self._info, **params)
        return ans



    def accept(self, remove_branch=False, sha=None):
        return self._api.call(PUT(
            '/projects/{0.project_id}/merge_requests/{0.iid}/merge'.format(self),
            dict(
                should_remove_source_branch=remove_branch,
                merge_when_pipeline_succeeds=True,
                sha=sha or self.sha,  # if provided, ensures what is merged is what we want (or fails)
            ),
        ))

    def assign_to(self, user_id):
        return self.update(assignee_id=user_id)

    def unassign(self):
        return self.assign_to(None)

    def fetch_approvals(self):
        # 'id' needed for for gitlab 9.2.2 hack (see Approvals.refetch_info())
        info = {'id': self.id, 'iid': self.iid, 'project_id': self.project_id}
        approvals = Approvals(self.api, info)
        approvals.refetch_info()
        return approvals
