from . import gitlab

GET, POST, PUT = gitlab.GET, gitlab.POST, gitlab.PUT


class Approvals(gitlab.Resource):
    """Approval info for a MergeRequest."""

    @classmethod
    def fetch_approvals_for_merge_request(cls, project_id, merge_request_iid, api):
        approvals = cls(api, {'iid': merge_request_iid, 'project_id': project_id})
        approvals.refetch_info()
        return approvals

    def refetch_info(self):
        approver_url = '/projects/{0.project_id}/merge_requests/{0.iid}/approvals'.format(self)
        self._info = self._api.call(GET(approver_url))

    @property
    def iid(self):
        return self.info['iid']

    @property
    def project_id(self):
        return self.info['project_id']

    @property
    def approvals_left(self):
        return self.info['approvals_left'] or 0

    @property
    def sufficient(self):
        return not self.info['approvals_left']

    @property
    def approver_usernames(self):
        return [who['user']['username'] for who in self.info['approved_by']]

    @property
    def approver_ids(self):
        """Return the uids of the approvers."""
        return [who['user']['id'] for who in self.info['approved_by']]

    def reapprove(self):
        """Impersonates the approvers and re-approves the merge_request as them.

        The idea is that we want to get the approvers, push the rebased branch
        (which may invalidate approvals, depending on gitlab settings) and then
        restore the approval status.
        """
        approve_url = '/projects/{0.project_id}/merge_requests/{0.iid}/approve'.format(self)
        for uid in self.approver_ids:
            self._api.call(POST(approve_url), sudo=uid)
