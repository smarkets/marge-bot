from unittest.mock import call, Mock, patch

import pytest

from marge.gitlab import Api, GET, POST, Version
from marge.approvals import Approvals, approvals_revoked_by_retarget
from marge.merge_request import MergeRequest
import marge.user
# testing this here is more convenient
from marge.job import CannotMerge, _get_reviewer_names_and_emails

INFO = {
    "id": 5,
    "iid": 6,
    "project_id": 1,
    "title": "Approvals API",
    "description": "Test",
    "state": "opened",
    "created_at": "2016-06-08T00:19:52.638Z",
    "updated_at": "2016-06-08T21:20:42.470Z",
    "merge_status": "can_be_merged",
    "approvals_required": 3,
    "approvals_left": 1,
    "approved_by": [
        {
            "user": {
                "name": "Administrator",
                "username": "root",
                "id": 1,
                "state": "active",
                "avatar_url": "".join([
                    "http://www.gravatar.com/avatar/",
                    "e64c7d89f26bd1972efa854d13d7dd61?s=80\u0026d=identicon",
                ]),
                "web_url": "http://localhost:3000/u/root"
            },
        },
        {
            "user": {
                "name": "Roger Ebert",
                "username": "ebert",
                "id": 2,
                "state": "active",
            }
        }
    ]
}
USERS = {
    1: {
        "name": "Administrator",
        "username": "root",
        "id": 1,
        "state": "active",
        "email": "root@localhost",
    },
    2: {
        "name": "Roger Ebert",
        "username": "ebert",
        "id": 2,
        "state": "active",
        "email": "ebert@example.com",
    },
}

APPROVED = 'approved this merge request'
UNAPPROVED = 'unapproved this merge request'
RETARGETED = 'changed target branch from `feature` to `master`'
RETARGETED_ON_DELETE = 'deleted the `feature` branch. This merge request now targets the `master` branch'


def mr_note(note_id, body, minute, author_id=1, system=True):
    return {
        'id': note_id,
        'body': body,
        'author': {'id': author_id},
        'system': system,
        'created_at': '2026-10-01T10:%02d:00.000Z' % minute,
    }


def mr_version(version_id, sha, minute):
    return {
        'id': version_id,
        'head_commit_sha': sha,
        'created_at': '2026-10-01T10:%02d:00.000Z' % minute,
    }


# pylint: disable=attribute-defined-outside-init
class TestApprovals:

    def setup_method(self, _method):
        self.api = Mock(Api)
        self.api.version = Mock(return_value=Version.parse('9.2.3-ee'))
        self.approvals = Approvals(api=self.api, info=INFO)

    def test_fetch_from_merge_request(self):
        api = self.api
        api.call = Mock(return_value=INFO)

        merge_request = MergeRequest(api, {'id': 74, 'iid': 6, 'project_id': 1234})
        approvals = merge_request.fetch_approvals()

        api.call.assert_called_once_with(GET(
            '/projects/1234/merge_requests/6/approvals'
        ))
        assert approvals.info == INFO

    def test_fetch_from_merge_request_ce_compat(self):
        api = self.api
        api.version = Mock(return_value=Version.parse('9.2.3'))
        api.call = Mock()

        merge_request = MergeRequest(api, {'id': 74, 'iid': 6, 'project_id': 1234})
        approvals = merge_request.fetch_approvals()

        api.call.assert_not_called()
        assert approvals.info == {
            'id': 74, 'iid': 6, 'project_id': 1234, 'approvals_left': 0, 'approved_by': [],
        }

    def test_properties(self):
        assert self.approvals.project_id == 1
        assert self.approvals.approvals_left == 1
        assert self.approvals.approver_usernames == ['root', 'ebert']
        assert not self.approvals.sufficient

    def test_sufficiency(self):
        good_approvals = Approvals(api=self.api, info=dict(INFO, approvals_required=1, approvals_left=0))
        assert good_approvals.sufficient

    def test_reapprove(self):
        self.approvals.reapprove()
        self.api.call.has_calls([
            call(POST(endpoint='/projects/1/merge_requests/6/approve', args={}, extract=None), sudo=1),
            call(POST(endpoint='/projects/1/merge_requests/6/approve', args={}, extract=None), sudo=2)
        ])

    @patch('marge.user.User.fetch_by_id')
    def test_get_reviewer_names_and_emails(self, user_fetch_by_id):
        user_fetch_by_id.side_effect = lambda id, _: marge.user.User(self.api, USERS[id])
        assert _get_reviewer_names_and_emails(commits=[], approvals=self.approvals, api=self.api) == [
            'Administrator <root@localhost>',
            'Roger Ebert <ebert@example.com>'
        ]

    @patch('marge.user.User.fetch_by_id')
    def test_approvals_fails_when_same_author(self, user_fetch_by_id):
        info = dict(INFO, approved_by=list(INFO['approved_by']))
        del info['approved_by'][1]
        approvals = Approvals(self.api, info)
        user_fetch_by_id.side_effect = lambda id, _: marge.user.User(self.api, USERS[id])
        commits = [{'author_email': 'root@localhost'}]
        with pytest.raises(CannotMerge):
            _get_reviewer_names_and_emails(commits=commits, approvals=approvals, api=self.api)

    @patch('marge.user.User.fetch_by_id')
    def test_approvals_succeeds_with_independent_author(self, user_fetch_by_id):
        user_fetch_by_id.side_effect = lambda id, _: marge.user.User(self.api, USERS[id])
        print(INFO['approved_by'])
        commits = [{'author_email': 'root@localhost'}]
        assert _get_reviewer_names_and_emails(commits=commits, approvals=self.approvals, api=self.api) == [
            'Administrator <root@localhost>',
            'Roger Ebert <ebert@example.com>',
        ]


class TestApprovalsRevokedByRetarget:
    versions = [mr_version(1, 'c0ffee', 0), mr_version(2, 'c0ffee', 3)]

    @pytest.mark.parametrize('retargeted', [RETARGETED, RETARGETED_ON_DELETE])
    def test_approvals_before_retarget(self, retargeted):
        notes = [
            mr_note(1, APPROVED, 1, author_id=1),
            mr_note(2, APPROVED, 2, author_id=2),
            mr_note(3, retargeted, 3),
        ]
        assert approvals_revoked_by_retarget(notes, self.versions, 'c0ffee') == [1, 2]
        assert approvals_revoked_by_retarget(notes[::-1], self.versions[::-1], 'c0ffee') == [1, 2]

    def test_not_retargeted(self):
        notes = [mr_note(1, APPROVED, 1)]
        assert approvals_revoked_by_retarget(notes, self.versions, 'c0ffee') == []

    def test_retargeted_twice(self):
        notes = [
            mr_note(1, APPROVED, 1, author_id=1),
            mr_note(2, RETARGETED, 2),
            mr_note(3, APPROVED, 2, author_id=2),
            mr_note(4, RETARGETED, 3),
        ]
        assert approvals_revoked_by_retarget(notes, self.versions, 'c0ffee') == [1, 2]

    def test_approved_again_after_retarget(self):
        notes = [mr_note(1, APPROVED, 1), mr_note(2, RETARGETED, 3), mr_note(3, APPROVED, 4)]
        assert approvals_revoked_by_retarget(notes, self.versions, 'c0ffee') == []

    def test_unapproved_before_retarget(self):
        notes = [mr_note(1, APPROVED, 1), mr_note(2, UNAPPROVED, 2), mr_note(3, RETARGETED, 3)]
        assert approvals_revoked_by_retarget(notes, self.versions, 'c0ffee') == []

    def test_unapproved_after_retarget(self):
        notes = [
            mr_note(1, APPROVED, 1),
            mr_note(2, RETARGETED, 3),
            mr_note(3, APPROVED, 4),
            mr_note(4, UNAPPROVED, 5),
        ]
        assert approvals_revoked_by_retarget(notes, self.versions, 'c0ffee') == []

    def test_ignores_comments(self):
        notes = [mr_note(1, APPROVED, 1, system=False), mr_note(2, RETARGETED, 3)]
        assert approvals_revoked_by_retarget(notes, self.versions, 'c0ffee') == []

        notes = [mr_note(1, APPROVED, 1), mr_note(2, RETARGETED, 3, system=False)]
        assert approvals_revoked_by_retarget(notes, self.versions, 'c0ffee') == []

    def test_ignores_approvals_of_previous_head(self):
        versions = [mr_version(1, 'dec0de', 0), mr_version(2, 'c0ffee', 2), mr_version(3, 'c0ffee', 4)]
        notes = [
            mr_note(1, APPROVED, 1, author_id=1),
            mr_note(2, APPROVED, 3, author_id=2),
            mr_note(3, RETARGETED, 4),
        ]
        assert approvals_revoked_by_retarget(notes, versions, 'c0ffee') == [2]

    def test_ignores_approvals_of_previous_head_with_the_same_sha(self):
        versions = [mr_version(1, 'c0ffee', 0), mr_version(2, 'dec0de', 2), mr_version(3, 'c0ffee', 3)]
        notes = [mr_note(1, APPROVED, 1), mr_note(2, RETARGETED, 4)]
        assert approvals_revoked_by_retarget(notes, versions, 'c0ffee') == []

    @pytest.mark.parametrize('sha', ['c0ffee', 'dec0de'])
    def test_pushed_after_retarget(self, sha):
        versions = self.versions + [mr_version(3, 'dec0de', 4)]
        notes = [mr_note(1, APPROVED, 1), mr_note(2, RETARGETED, 3)]
        assert approvals_revoked_by_retarget(notes, versions, sha) == []

    def test_no_versions(self):
        notes = [mr_note(1, APPROVED, 1), mr_note(2, RETARGETED, 3)]
        assert approvals_revoked_by_retarget(notes, [], 'c0ffee') == []
