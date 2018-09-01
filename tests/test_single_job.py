import contextlib
from collections import namedtuple
from datetime import timedelta
from unittest.mock import ANY, patch, create_autospec

import pytest

import marge.commit
import marge.interval
import marge.git
import marge.gitlab
import marge.job
import marge.project
import marge.single_merge_job
import marge.user
from marge.gitlab import GET, PUT
from marge.merge_request import MergeRequest
from tests.gitlab_api_mock import Error, Ok, MockLab


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


class SingleJobMockLab(MockLab):
    def __init__(self, gitlab_url=None, fork=False):
        super().__init__(gitlab_url, fork=fork)
        api = self.api
        self.rewritten_sha = rewritten_sha = 'af7a'
        api.add_pipelines(
            self.merge_request_info['source_project_id'],
            _pipeline(sha1=rewritten_sha, status='running'),
            from_state='pushed', to_state='passed',
        )
        api.add_pipelines(
            self.merge_request_info['source_project_id'],
            _pipeline(sha1=rewritten_sha, status='success'),
            from_state=['passed', 'merged'],
        )
        source_project_id = self.merge_request_info['source_project_id']
        api.add_transition(
            GET('/projects/{}/repository/branches/useless_new_feature'.format(source_project_id)),
            Ok({'commit': _commit(commit_id=rewritten_sha, status='running')}),
            from_state='pushed',
        )
        api.add_transition(
            GET('/projects/{}/repository/branches/useless_new_feature'.format(source_project_id)),
            Ok({'commit': _commit(commit_id=rewritten_sha, status='success')}),
            from_state='passed'
        )
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/{iid}/merge'.format(iid=self.merge_request_info['iid']),
                dict(sha=rewritten_sha, should_remove_source_branch=True, merge_when_pipeline_succeeds=True),
            ),
            Ok({}),
            from_state='passed', to_state='merged',
        )
        api.add_merge_request(dict(self.merge_request_info, state='merged'), from_state='merged')
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
            PUT(
                '/projects/1234/merge_requests/{iid}'.format(iid=self.merge_request_info['iid']),
                args={'assignee_id': self.author_id},
            ),
            assign_to_author,
        )
        error_note = "I couldn't merge this branch: %s" % message
        self.api.expected_note(self.merge_request_info, error_note)

        yield

        assert author_assigned
        assert error_note in self.api.notes

    @contextlib.contextmanager
    def branch_update(self, side_effect=None):
        if side_effect is None:
            side_effect = self.push_updated
        with patch.object(
                marge.single_merge_job.SingleMergeJob,
                'update_from_target_branch_and_push',
                side_effect=side_effect,
                autospec=True,
        ):
            yield


class TestUpdateAndAccept(object):
    TestParams = namedtuple('TestParams', ['fork', 'source_project_id'])

    @pytest.fixture(
        params=[
            TestParams(fork=True, source_project_id=4321),
            TestParams(fork=False, source_project_id=1234),
        ]
    )
    def test_params(self, request):
        return request.param

    @pytest.fixture(autouse=True)
    def patch_sleep(self):
        with patch('time.sleep'):
            yield

    @pytest.fixture()
    def mocklab(self, test_params):
        print('fork: %s' % test_params.fork)
        return SingleJobMockLab(fork=test_params.fork)

    @pytest.fixture()
    def api(self, mocklab):
        return mocklab.api

    def make_job(self, api, mocklab, options=None):
        project_id = mocklab.project_info['id']
        merge_request_iid = mocklab.merge_request_info['iid']

        project = marge.project.Project.fetch_by_id(project_id, api)
        merge_request = MergeRequest.fetch_by_iid(project_id, merge_request_iid, api)

        repo = create_autospec(marge.git.Repo, spec_set=True)
        options = options or marge.job.MergeJobOptions.default()
        user = marge.user.User.myself(api)
        return marge.single_merge_job.SingleMergeJob(
            api=api, user=user,
            project=project, merge_request=merge_request, repo=repo,
            options=options,
        )

    def test_succeeds_first_time(self, api, mocklab):
        with mocklab.branch_update():
            job = self.make_job(
                api,
                mocklab,
                options=marge.job.MergeJobOptions.default(add_tested=True, add_reviewers=False),
            )
            job.execute()

        assert api.state == 'merged'
        assert api.notes == []

    def test_fails_on_not_acceptable_if_master_did_not_move(
            self, api, mocklab, test_params
    ):
        new_branch_head_sha = '99ba110035'
        api.add_transition(
            GET(
                '/projects/{source_project_id}/repository/branches/useless_new_feature'.format(
                    source_project_id=test_params.source_project_id,
                ),
            ),
            Ok({'commit': _commit(commit_id=new_branch_head_sha, status='success')}),
            from_state='pushed', to_state='pushed_but_head_changed'
        )
        with mocklab.branch_update():
            with mocklab.expected_failure("Someone pushed to branch while we were trying to merge"):
                job = self.make_job(
                    api,
                    mocklab,
                    options=marge.job.MergeJobOptions.default(add_tested=True, add_reviewers=False),
                )
                job.execute()

        assert api.state == 'pushed_but_head_changed'
        assert api.notes == [
            "I couldn't merge this branch: Someone pushed to branch while we were trying to merge",
        ]

    def test_succeeds_second_time_if_master_moved(self, api, mocklab, test_params):
        moved_master_sha = 'fafafa'
        first_rewritten_sha = '1o1'
        api.add_pipelines(
            mocklab.merge_request_info['source_project_id'],
            _pipeline(sha1=first_rewritten_sha, status='success'),
            from_state=['pushed_but_master_moved', 'merged_rejected'],
        )
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/{iid}/merge'.format(iid=mocklab.merge_request_info['iid']),
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
            GET(
                '/projects/{source_project_id}/repository/branches/useless_new_feature'.format(
                    source_project_id=test_params.source_project_id,
                ),
            ),
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

        with mocklab.branch_update(side_effect=push_effects()):
            job = self.make_job(
                api,
                mocklab,
                options=marge.job.MergeJobOptions.default(add_tested=True, add_reviewers=False),
            )
            job.execute()

        assert api.state == 'merged'
        assert api.notes == [
            "My job would be easier if people didn't jump the queue and push directly... *sigh*",
        ]

    def test_handles_races_for_merging(self, api, mocklab):
        rewritten_sha = mocklab.rewritten_sha
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/{iid}/merge'.format(iid=mocklab.merge_request_info['iid']),
                dict(sha=rewritten_sha, should_remove_source_branch=True, merge_when_pipeline_succeeds=True),
            ),
            Error(marge.gitlab.NotFound(404, {'message': '404 Branch Not Found'})),
            from_state='passed', to_state='someone_else_merged',
        )
        api.add_merge_request(
            dict(mocklab.merge_request_info, state='merged'),
            from_state='someone_else_merged',
        )
        with mocklab.branch_update():
            job = self.make_job(api, mocklab)
            job.execute()
        assert api.state == 'someone_else_merged'
        assert api.notes == []

    def test_handles_request_becoming_wip_after_push(self, api, mocklab):
        rewritten_sha = mocklab.rewritten_sha
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/{iid}/merge'.format(iid=mocklab.merge_request_info['iid']),
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
        with mocklab.branch_update(), mocklab.expected_failure(message):
            job = self.make_job(api, mocklab)
            job.execute()
        assert api.state == 'now_is_wip'
        assert api.notes == ["I couldn't merge this branch: %s" % message]

    def test_guesses_git_hook_error_on_merge_refusal(self, api, mocklab):
        rewritten_sha = mocklab.rewritten_sha
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/{iid}/merge'.format(iid=mocklab.merge_request_info['iid']),
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
        with mocklab.branch_update(), mocklab.expected_failure(message):
            job = self.make_job(api, mocklab)
            job.execute()
        assert api.state == 'rejected_by_git_hook'
        assert api.notes == ["I couldn't merge this branch: %s" % message]

    def test_discovers_if_someone_closed_the_merge_request(self, api, mocklab):
        rewritten_sha = mocklab.rewritten_sha
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/{iid}/merge'.format(iid=mocklab.merge_request_info['iid']),
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
        with mocklab.branch_update(), mocklab.expected_failure(message):
            job = self.make_job(api, mocklab)
            job.execute()
        assert api.state == 'oops_someone_closed_it'
        assert api.notes == ["I couldn't merge this branch: %s" % message]

    def test_tells_explicitly_that_gitlab_refused_to_merge(self, api, mocklab):
        rewritten_sha = mocklab.rewritten_sha
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/{iid}/merge'.format(iid=mocklab.merge_request_info['iid']),
                dict(sha=rewritten_sha, should_remove_source_branch=True, merge_when_pipeline_succeeds=True),
            ),
            Error(marge.gitlab.MethodNotAllowed(405, {'message': '405 Method Not Allowed'})),
            from_state='passed', to_state='rejected_for_mysterious_reasons',
        )
        message = "Gitlab refused to merge this request and I don't know why!"
        with mocklab.branch_update(), mocklab.expected_failure(message):
            job = self.make_job(api, mocklab)
            job.execute()
        assert api.state == 'rejected_for_mysterious_reasons'
        assert api.notes == ["I couldn't merge this branch: %s" % message]

    def test_wont_merge_wip_stuff(self, api, mocklab):
        wip_merge_request = dict(mocklab.merge_request_info, work_in_progress=True)
        api.add_merge_request(wip_merge_request, from_state='initial')

        with mocklab.expected_failure("Sorry, I can't merge requests marked as Work-In-Progress!"):
            job = self.make_job(api, mocklab)
            job.execute()

        assert api.state == 'initial'
        assert api.notes == [
            "I couldn't merge this branch: Sorry, I can't merge requests marked as Work-In-Progress!",
        ]

    def test_wont_merge_branches_with_autosquash_if_rewriting(self, api, mocklab):
        autosquash_merge_request = dict(mocklab.merge_request_info, squash=True)
        api.add_merge_request(autosquash_merge_request, from_state='initial')
        admin_user = dict(mocklab.user_info, is_admin=True)
        api.add_user(admin_user, is_current=True)

        message = "Sorry, merging requests marked as auto-squash would ruin my commit tagging!"

        for rewriting_opt in ('add_tested', 'add_reviewers'):
            with mocklab.expected_failure(message):
                job = self.make_job(
                    api,
                    mocklab,
                    options=marge.job.MergeJobOptions.default(**{rewriting_opt: True}),
                )
                job.execute()

            assert api.state == 'initial'

        with mocklab.branch_update():
            job = self.make_job(api, mocklab)
            job.execute()
        assert api.state == 'merged'

    @patch('marge.job.log', autospec=True)
    def test_waits_for_approvals(self, mock_log, api, mocklab):
        with mocklab.branch_update():
            job = self.make_job(
                api,
                mocklab,
                options=marge.job.MergeJobOptions.default(
                    approval_timeout=timedelta(seconds=5), reapprove=True,
                ),
            )
            job.execute()

        mock_log.info.assert_any_call('Checking if approvals have reset')
        mock_log.debug.assert_any_call('Approvals haven\'t reset yet, sleeping for %s secs', ANY)
        assert api.state == 'merged'

    def test_fails_if_changes_already_exist(self, api, mocklab):
        expected_message = 'these changes already exist in branch `{}`'.format(
            mocklab.merge_request_info['target_branch'],
        )
        with mocklab.expected_failure(expected_message):
            job = self.make_job(api, mocklab)
            job.repo.rebase.return_value = mocklab.initial_master_sha
            job.repo.get_commit_hash.return_value = mocklab.initial_master_sha
            job.execute()

        assert api.state == 'initial'
        assert api.notes == ["I couldn't merge this branch: {}".format(expected_message)]
