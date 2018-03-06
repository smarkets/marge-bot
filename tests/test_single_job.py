import contextlib
from datetime import timedelta
from unittest.mock import ANY, Mock, patch

import marge.commit
import marge.interval
import marge.git
import marge.gitlab
import marge.job
import marge.project
import marge.single_merge_job
import marge.user
from marge.gitlab import GET, PUT
from marge.job import MergeJobOptions
from marge.merge_request import MergeRequest

import tests.test_approvals as test_approvals
import tests.test_commit as test_commit
import tests.test_project as test_project
import tests.test_user as test_user
from tests.gitlab_api_mock import Api as ApiMock, Error, Ok


def _commit(commit_id, status):
    return {
        'id': commit_id,
        'short_id': commit_id,
        'author_name': 'J. Bond',
        'author_email': 'jbond@mi6.gov.uk',
        'message': 'Shaken, not stirred',
        'status': status,
    }


def _pipeline(sha1, status):
    return {
        'id': 47,
        'status': status,
        'ref': 'useless_new_feature',
        'sha': sha1,
    }


class MockLab(object):
    def __init__(self, gitlab_url=None):
        self.gitlab_url = gitlab_url = gitlab_url or 'http://git.example.com'
        self.api = api = ApiMock(gitlab_url=gitlab_url, auth_token='no-token', initial_state='initial')

        api.add_transition(GET('/version'), Ok({'version': '9.2.3-ee'}))

        self.user_info = dict(test_user.INFO)
        self.user_id = self.user_info['id']
        api.add_user(self.user_info, is_current=True)

        self.project_info = dict(test_project.INFO)
        api.add_project(self.project_info)

        self.commit_info = dict(test_commit.INFO)
        api.add_commit(self.project_info['id'], self.commit_info)

        self.author_id = 234234
        self.merge_request_info = {
            'id':  53,
            'iid': 54,
            'title': 'a title',
            'project_id': 1234,
            'author': {'id': self.author_id},
            'assignee': {'id': self.user_id},
            'approved_by': [],
            'state': 'opened',
            'sha': self.commit_info['id'],
            'source_project_id': 1234,
            'target_project_id': 1234,
            'source_branch': 'useless_new_feature',
            'target_branch': 'master',
            'work_in_progress': False,
            'web_url': 'http://git.example.com/group/project/merge_request/666',
        }
        api.add_merge_request(self.merge_request_info)

        self.initial_master_sha = '505e'
        self.rewritten_sha = rewritten_sha = 'af7a'
        api.add_pipelines(
            self.project_info['id'],
            _pipeline(sha1=rewritten_sha, status='running'),
            from_state='pushed', to_state='passed',
        )
        api.add_pipelines(
            self.project_info['id'],
            _pipeline(sha1=rewritten_sha, status='success'),
            from_state=['passed', 'merged'],
        )
        api.add_transition(
            GET('/projects/1234/repository/branches/useless_new_feature'),
            Ok({'commit': _commit(commit_id=rewritten_sha, status='running')}),
            from_state='pushed',
        )
        api.add_transition(
            GET('/projects/1234/repository/branches/useless_new_feature'),
            Ok({'commit': _commit(commit_id=rewritten_sha, status='success')}),
            from_state='passed'
        )
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/54/merge',
                dict(sha=rewritten_sha, should_remove_source_branch=True, merge_when_pipeline_succeeds=True),
            ),
            Ok({}),
            from_state='passed', to_state='merged',
        )
        api.add_merge_request(dict(self.merge_request_info, state='merged'), from_state='merged')
        self.approvals_info = dict(
            test_approvals.INFO,
            id=self.merge_request_info['id'],
            iid=self.merge_request_info['iid'],
            project_id=self.merge_request_info['project_id'],
            approvals_left=0,
        )
        api.add_approvals(self.approvals_info)
        api.add_transition(
            GET('/projects/1234/repository/branches/master'),
            Ok({'commit': {'id': self.initial_master_sha}}),
        )
        api.add_transition(
            GET('/projects/1234/repository/branches/master'),
            Ok({'commit': {'id': self.rewritten_sha}}),
            from_state='merged'
        )
        api.expected_note(
            self.merge_request_info,
            "My job would be easier if people didn't jump the queue and push directly... *sigh*",
            from_state=['pushed_but_master_moved', 'merge_rejected'],
        )
        api.expected_note(
            self.merge_request_info,
            "I'm broken on the inside, please somebody fix me... :cry:"
        )

    def push_updated(self, *unused_args, **unused_kwargs):
        self.api.state = 'pushed'
        updated_sha = 'deadbeef'
        return self.initial_master_sha, updated_sha, self.rewritten_sha

    @contextlib.contextmanager
    def expected_failure(self, message):
        author_assigned = False

        def assign_to_author():
            nonlocal author_assigned
            author_assigned = True

        self.api.add_transition(
            PUT('/projects/1234/merge_requests/54', args={'assignee_id': self.author_id}),
            assign_to_author,
        )
        error_note = "I couldn't merge this branch: %s" % message
        self.api.expected_note(self.merge_request_info, error_note)

        yield

        assert author_assigned
        assert error_note in self.api.notes


# pylint: disable=attribute-defined-outside-init
@patch('time.sleep')
class TestUpdateAndAccept(object):

    def setup_method(self, _method):
        self.mocklab = MockLab()
        self.api = self.mocklab.api

    def make_job(self, options=None):
        api, mocklab = self.api, self.mocklab

        project_id = mocklab.project_info['id']
        merge_request_iid = mocklab.merge_request_info['iid']

        project = marge.project.Project.fetch_by_id(project_id, api)
        merge_request = MergeRequest.fetch_by_iid(project_id, merge_request_iid, api)

        repo = Mock(marge.git.Repo)
        options = options or marge.job.MergeJobOptions.default()
        user = marge.user.User.myself(self.api)
        return marge.single_merge_job.SingleMergeJob(
            api=api, user=user,
            project=project, merge_request=merge_request, repo=repo,
            options=options,
        )

    def test_succeeds_first_time(self, unused_time_sleep):
        api, mocklab = self.api, self.mocklab
        with patch.object(
                marge.single_merge_job.SingleMergeJob,
                'update_from_target_branch_and_push',
                side_effect=mocklab.push_updated,
        ):
            job = self.make_job(marge.job.MergeJobOptions.default(add_tested=True, add_reviewers=False))
            job.execute()

        assert api.state == 'merged'
        assert api.notes == []

    def test_fails_on_not_acceptable_if_master_did_not_move(self, unused_time_sleep):
        api, mocklab = self.api, self.mocklab
        new_branch_head_sha = '99ba110035'
        api.add_transition(
            GET('/projects/1234/repository/branches/useless_new_feature'),
            Ok({'commit': _commit(commit_id=new_branch_head_sha, status='success')}),
            from_state='pushed', to_state='pushed_but_head_changed'
        )
        with patch.object(
                marge.single_merge_job.SingleMergeJob,
                'update_from_target_branch_and_push',
                side_effect=mocklab.push_updated,
        ):
            with mocklab.expected_failure("Someone pushed to branch while we were trying to merge"):
                job = self.make_job(marge.job.MergeJobOptions.default(add_tested=True, add_reviewers=False))
                job.execute()

        assert api.state == 'pushed_but_head_changed'
        assert api.notes == [
            "I couldn't merge this branch: Someone pushed to branch while we were trying to merge",
        ]

    def test_succeeds_second_time_if_master_moved(self, unused_time_sleep):
        api, mocklab = self.api, self.mocklab
        moved_master_sha = 'fafafa'
        first_rewritten_sha = '1o1'
        api.add_pipelines(
            mocklab.project_info['id'],
            _pipeline(sha1=first_rewritten_sha, status='success'),
            from_state=['pushed_but_master_moved', 'merged_rejected'],
        )
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/54/merge',
                dict(
                    sha=first_rewritten_sha,
                    should_remove_source_branch=True,
                    merge_when_pipeline_succeeds=True,
                ),
            ),
            Error(marge.gitlab.NotAcceptable()),
            from_state='pushed_but_master_moved', to_state='merge_rejected',
        )
        api.add_transition(
            GET('/projects/1234/repository/branches/useless_new_feature'),
            Ok({'commit': _commit(commit_id=first_rewritten_sha, status='success')}),
            from_state='pushed_but_master_moved'
        )
        api.add_transition(
            GET('/projects/1234/repository/branches/master'),
            Ok({'commit': _commit(commit_id=moved_master_sha, status='success')}),
            from_state='merge_rejected'
        )

        def push_effects():
            assert api.state == 'initial'
            api.state = 'pushed_but_master_moved'
            yield mocklab.initial_master_sha, 'f00ba4', first_rewritten_sha

            assert api.state == 'merge_rejected'
            api.state = 'pushed'
            yield moved_master_sha, 'deadbeef', mocklab.rewritten_sha

        with patch.object(
                marge.single_merge_job.SingleMergeJob,
                'update_from_target_branch_and_push',
                side_effect=push_effects(),
        ):
            job = self.make_job(marge.job.MergeJobOptions.default(add_tested=True, add_reviewers=False))
            job.execute()

        assert api.state == 'merged'
        assert api.notes == [
            "My job would be easier if people didn't jump the queue and push directly... *sigh*",
        ]

    def test_handles_races_for_merging(self, unused_time_sleep):
        api, mocklab = self.api, self.mocklab
        rewritten_sha = mocklab.rewritten_sha
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/54/merge',
                dict(sha=rewritten_sha, should_remove_source_branch=True, merge_when_pipeline_succeeds=True),
            ),
            Error(marge.gitlab.NotFound(404, {'message': '404 Branch Not Found'})),
            from_state='passed', to_state='someone_else_merged',
        )
        api.add_merge_request(
            dict(mocklab.merge_request_info, state='merged'),
            from_state='someone_else_merged',
        )
        with patch.object(
                marge.single_merge_job.SingleMergeJob,
                'update_from_target_branch_and_push',
                side_effect=mocklab.push_updated,
        ):
            job = self.make_job()
            job.execute()
        assert api.state == 'someone_else_merged'
        assert api.notes == []

    def test_handles_request_becoming_wip_after_push(self, unused_time_sleep):
        api, mocklab = self.api, self.mocklab
        rewritten_sha = mocklab.rewritten_sha
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/54/merge',
                dict(sha=rewritten_sha, should_remove_source_branch=True, merge_when_pipeline_succeeds=True),
            ),
            Error(marge.gitlab.MethodNotAllowed(405, {'message': '405 Method Not Allowed'})),
            from_state='passed', to_state='now_is_wip',
        )
        api.add_merge_request(
            dict(mocklab.merge_request_info, work_in_progress=True),
            from_state='now_is_wip',
        )
        message = 'The request was marked as WIP as I was processing it (maybe a WIP commit?)'
        with patch.object(
                marge.single_merge_job.SingleMergeJob,
                'update_from_target_branch_and_push',
                side_effect=mocklab.push_updated,
        ):
            with mocklab.expected_failure(message):
                job = self.make_job()
                job.execute()
        assert api.state == 'now_is_wip'
        assert api.notes == ["I couldn't merge this branch: %s" % message]

    def test_guesses_git_hook_error_on_merge_refusal(self, unused_time_sleep):
        api, mocklab = self.api, self.mocklab
        rewritten_sha = mocklab.rewritten_sha
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/54/merge',
                dict(sha=rewritten_sha, should_remove_source_branch=True, merge_when_pipeline_succeeds=True),
            ),
            Error(marge.gitlab.MethodNotAllowed(405, {'message': '405 Method Not Allowed'})),
            from_state='passed', to_state='rejected_by_git_hook',
        )
        api.add_merge_request(
            dict(mocklab.merge_request_info, state='reopened'),
            from_state='rejected_by_git_hook',
        )
        message = (
            'GitLab refused to merge this branch. I suspect that a Push Rule or a git-hook '
            'is rejecting my commits; maybe my email needs to be white-listed?'
        )
        with patch.object(
                marge.single_merge_job.SingleMergeJob,
                'update_from_target_branch_and_push',
                side_effect=mocklab.push_updated,
        ):
            with mocklab.expected_failure(message):
                job = self.make_job()
                job.execute()
        assert api.state == 'rejected_by_git_hook'
        assert api.notes == ["I couldn't merge this branch: %s" % message]

    def test_discovers_if_someone_closed_the_merge_request(self, unused_time_sleep):
        api, mocklab = self.api, self.mocklab
        rewritten_sha = mocklab.rewritten_sha
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/54/merge',
                dict(sha=rewritten_sha, should_remove_source_branch=True, merge_when_pipeline_succeeds=True),
            ),
            Error(marge.gitlab.MethodNotAllowed(405, {'message': '405 Method Not Allowed'})),
            from_state='passed', to_state='oops_someone_closed_it',
        )
        api.add_merge_request(
            dict(mocklab.merge_request_info, state='closed'),
            from_state='oops_someone_closed_it',
        )
        message = 'Someone closed the merge request while I was attempting to merge it.'
        with patch.object(
                marge.single_merge_job.SingleMergeJob,
                'update_from_target_branch_and_push',
                side_effect=mocklab.push_updated,
        ):
            with mocklab.expected_failure(message):
                job = self.make_job()
                job.execute()
        assert api.state == 'oops_someone_closed_it'
        assert api.notes == ["I couldn't merge this branch: %s" % message]

    def test_tells_explicitly_that_gitlab_refused_to_merge(self, unused_time_sleep):
        api, mocklab = self.api, self.mocklab
        rewritten_sha = mocklab.rewritten_sha
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/54/merge',
                dict(sha=rewritten_sha, should_remove_source_branch=True, merge_when_pipeline_succeeds=True),
            ),
            Error(marge.gitlab.MethodNotAllowed(405, {'message': '405 Method Not Allowed'})),
            from_state='passed', to_state='rejected_for_mysterious_reasons',
        )
        message = "Gitlab refused to merge this request and I don't know why!"
        with patch.object(
                marge.single_merge_job.SingleMergeJob,
                'update_from_target_branch_and_push',
                side_effect=mocklab.push_updated,
        ):
            with mocklab.expected_failure(message):
                job = self.make_job()
                job.execute()
        assert api.state == 'rejected_for_mysterious_reasons'
        assert api.notes == ["I couldn't merge this branch: %s" % message]

    def test_wont_merge_wip_stuff(self, unused_time_sleep):
        api, mocklab = self.api, self.mocklab
        wip_merge_request = dict(mocklab.merge_request_info, work_in_progress=True)
        api.add_merge_request(wip_merge_request, from_state='initial')

        with mocklab.expected_failure("Sorry, I can't merge requests marked as Work-In-Progress!"):
            job = self.make_job()
            job.execute()

        assert api.state == 'initial'
        assert api.notes == [
            "I couldn't merge this branch: Sorry, I can't merge requests marked as Work-In-Progress!",
        ]

    def test_wont_merge_branches_with_autosquash_if_rewriting(self, unused_time_sleep):
        api, mocklab = self.api, self.mocklab
        autosquash_merge_request = dict(mocklab.merge_request_info, squash=True)
        api.add_merge_request(autosquash_merge_request, from_state='initial')
        admin_user = dict(mocklab.user_info, is_admin=True)
        api.add_user(admin_user, is_current=True)

        message = "Sorry, merging requests marked as auto-squash would ruin my commit tagging!"

        for rewriting_opt in ('add_tested', 'add_reviewers'):
            with mocklab.expected_failure(message):
                job = self.make_job(marge.job.MergeJobOptions.default(**{rewriting_opt: True}))
                job.execute()

            assert api.state == 'initial'

        with patch.object(
                marge.single_merge_job.SingleMergeJob,
                'update_from_target_branch_and_push',
                side_effect=mocklab.push_updated,
        ):
            job = self.make_job()
            job.execute()
        assert api.state == 'merged'

    @patch('marge.job.log')
    def test_waits_for_approvals(self, mock_log, unused_time_sleep):
        api, mocklab = self.api, self.mocklab
        with patch.object(
                marge.single_merge_job.SingleMergeJob,
                'update_from_target_branch_and_push',
                side_effect=mocklab.push_updated,
        ):
            job = self.make_job(
                marge.job.MergeJobOptions.default(approval_timeout=timedelta(seconds=5), reapprove=True))
            job.execute()

        mock_log.info.assert_any_call('Checking if approvals have reset')
        mock_log.debug.assert_any_call('Approvals haven\'t reset yet, sleeping for %s secs', ANY)
        assert api.state == 'merged'

    def test_fails_if_changes_already_exist(self, unused_time_sleep):
        api, mocklab = self.api, self.mocklab
        expected_message = 'these changes already exist in branch `{}`'.format(
            mocklab.merge_request_info['target_branch'],
        )
        with mocklab.expected_failure(expected_message):
            job = self.make_job()
            job.repo.rebase.return_value = mocklab.initial_master_sha
            job.repo.get_commit_hash.return_value = mocklab.initial_master_sha
            job.execute()

        assert api.state == 'initial'
        assert api.notes == ["I couldn't merge this branch: {}".format(expected_message)]


class TestMergeJobOptions(object):
    def test_default(self):
        assert MergeJobOptions.default() == MergeJobOptions(
            add_tested=False,
            add_part_of=False,
            add_reviewers=False,
            reapprove=False,
            approval_timeout=timedelta(seconds=0),
            embargo=marge.interval.IntervalUnion.empty(),
            ci_timeout=timedelta(minutes=15),
            use_merge_strategy=False,
        )

    def test_default_ci_time(self):
        three_min = timedelta(minutes=3)
        assert MergeJobOptions.default(ci_timeout=three_min) == MergeJobOptions.default()._replace(
            ci_timeout=three_min
        )
