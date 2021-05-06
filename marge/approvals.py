import yaml
import logging as log

from . import gitlab

GET, POST, PUT = gitlab.GET, gitlab.POST, gitlab.PUT


class Approvals(gitlab.Resource):
    """Approval info for a MergeRequest."""

    def refetch_info(self):
        gitlab_version = self._api.version()
        if gitlab_version.release >= (9, 2, 2):
            approver_url = '/projects/{0.project_id}/merge_requests/{0.iid}/approvals'.format(self)
        else:
            # GitLab botched the v4 api before 9.2.3
            approver_url = '/projects/{0.project_id}/merge_requests/{0.id}/approvals'.format(self)

        if gitlab_version.is_ee:
            self._info = self._api.call(GET(approver_url))
        else:
            self.get_approvers_ce()

    def get_approvers_ce(self):
        """get approvers status using thumbs on merge request
        """

        config_file = self._api.repo_file_get(self.project_id, ".marge-bot.yml", "master")
        if config_file is None:
            log.info('Project id %s missing .marge-bot.yaml', self.project_id)
            config = {}
        else:
            config = yaml.load(config_file["content"])


        emoji_url = '/projects/{0.project_id}/merge_requests/{0.iid}/award_emoji'
        emoji_url = emoji_url.format(self)
        emoji = self._api.call(GET(emoji_url))

        up_votes = [e  for e in emoji if e['name'] == 'thumbsup']
        approver_count = config.get('approver_count', 1)
        approvals_left = max(approver_count - len(up_votes), 0)
        self._info = dict(self._info, approvals_left=approvals_left, approved_by=up_votes)

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
