import re

import maya

from . import gitlab

GET, POST, PUT = gitlab.GET, gitlab.POST, gitlab.PUT

_APPROVED_NOTE = 'approved this merge request'
_UNAPPROVED_NOTE = 'unapproved this merge request'
_RETARGETED_NOTE = re.compile(
    r'changed target branch from '
    r'|deleted the `.+` branch\. This merge request now targets '
)


class Approvals(gitlab.Resource):
    """Approval info for a MergeRequest."""

    def refetch_info(self):
        gitlab_version = self._api.version()
        if gitlab_version.release >= (9, 2, 2):
            approver_url = '/projects/{0.project_id}/merge_requests/{0.iid}/approvals'.format(self)
        else:
            # GitLab botched the v4 api before 9.2.3
            approver_url = '/projects/{0.project_id}/merge_requests/{0.id}/approvals'.format(self)

        # Approvals are in CE since 13.2
        if gitlab_version.is_ee or gitlab_version.release >= (13, 2, 0):
            self._info = self._api.call(GET(approver_url))
        else:
            self._info = dict(self._info, approvals_left=0, approved_by=[])

    @property
    def iid(self):
        return self.info['iid']

    @property
    def project_id(self):
        return self.info['project_id']

    @property
    def approvals_left(self):
        return self.info.get("approvals_left", 0) or 0

    @property
    def sufficient(self):
        return not self.approvals_left

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
        (which may invalidate approvals, depending on GitLab settings) and then
        restore the approval status.
        """
        self.approve(self)

    def approve(self, obj):
        """Approve an object which can be a merge_request or an approval."""
        if self._api.version().release >= (9, 2, 2):
            approve_url = '/projects/{0.project_id}/merge_requests/{0.iid}/approve'.format(obj)
        else:
            # GitLab botched the v4 api before 9.2.3
            approve_url = '/projects/{0.project_id}/merge_requests/{0.id}/approve'.format(obj)

        for uid in self.approver_ids:
            self._api.call(POST(approve_url), sudo=uid)


def approvals_revoked_by_retarget(notes, versions, sha):
    head_since = None
    for version in sorted(versions, key=lambda version: version['id'], reverse=True):
        if version['head_commit_sha'] != sha:
            break
        head_since = _parse_time(version['created_at'])
    if head_since is None:
        return []

    retargeted_since_approval = {}
    for note in sorted(notes, key=lambda note: note['id']):
        if not note['system'] or _parse_time(note['created_at']) < head_since:
            continue
        if note['body'] == _APPROVED_NOTE:
            retargeted_since_approval[note['author']['id']] = False
        elif note['body'] == _UNAPPROVED_NOTE:
            retargeted_since_approval.pop(note['author']['id'], None)
        elif _RETARGETED_NOTE.match(note['body']):
            retargeted_since_approval = dict.fromkeys(retargeted_since_approval, True)
    return [uid for uid, retargeted in retargeted_since_approval.items() if retargeted]


def _parse_time(timestamp):
    return maya.parse(timestamp).datetime()
