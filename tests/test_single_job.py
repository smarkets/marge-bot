# pylint: disable=too-many-locals
import contextlib
from collections import namedtuple
from datetime import timedelta
from functools import partial
from unittest.mock import ANY, patch

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
from marge.job import Fusion
from marge.merge_request import MergeRequest
from tests.git_repo_mock import RepoMock
from tests.gitlab_api_mock import Error, Ok, MockLab
import tests.test_commit as test_commit


INITIAL_MR_SHA = test_commit.INFO['id']


def _commit(commit_id, status):
    return {
        'id': commit_id,
        'short_id': commit_id,
        'author_name': 'J. Bond',
        'author_email': 'jbond@mi6.gov.uk',
        'message': 'Shaken, not stirred',
        'status': status,
    }


def _branch(name, protected=False):
    return {
        'name': name,
        'protected': protected,
    }


def _pipeline(sha1, status, ref='useless_new_feature'):
    return {
        'id': 47,
        'status': status,
        'ref': ref,
        'sha': sha1,
        'jobs': [{'name': 'job1'}, {'name': 'job2'}],
    }


class SingleJobMockLab(MockLab):
    def __init__(
        self,
        *,
        initial_master_sha,
        rewritten_sha,
        gitlab_url=None,
        fork=False,
        expect_gitlab_rebase=False,
        merge_request_options=None,
    ):
        super().__init__(
            initial_master_sha,
            gitlab_url,
            fork=fork,
            merge_request_options=merge_request_options,
        )
        api = self.api
        self.rewritten_sha = rewritten_sha
        if expect_gitlab_rebase:
            api.add_transition(
                PUT(
                    '/projects/{project_id}/merge_requests/{iid}/rebase'.format(
                        project_id=self.merge_request_info['project_id'],
                        iid=self.merge_request_info['iid'],
                    ),
                ),
                Ok(True),
                from_state='initial',
                to_state='rebase-in-progress',
            )
            api.add_merge_request(
               dict(self.merge_request_info, rebase_in_progress=True),
               from_state='rebase-in-progress',
               to_state='rebase-finished'
            )
            api.add_merge_request(
               dict(
                 self.merge_request_info,
                 rebase_in_progress=False,
                 sha=rewritten_sha,
               ),
               from_state='rebase-finished',
               to_state='pushed',
            )

        api.add_pipelines(
            self.merge_request_info['source_project_id'],
            _pipeline(sha1=rewritten_sha, status='running', ref=self.merge_request_info['source_branch']),
            from_state='pushed', to_state='passed',
        )
        api.add_pipelines(
            self.merge_request_info['source_project_id'],
            _pipeline(sha1=rewritten_sha, status='success', ref=self.merge_request_info['source_branch']),
            from_state=['passed', 'merged'],
        )
        source_project_id = self.merge_request_info['source_project_id']
        api.add_transition(
            GET(
                '/projects/{}/repository/branches/{}'.format(
                    source_project_id, self.merge_request_info['source_branch'],
                ),
            ),
            Ok({'commit': _commit(commit_id=rewritten_sha, status='running')}),
            from_state='pushed',
        )
        api.add_transition(
            GET(
                '/projects/{}/repository/branches/{}'.format(
                    source_project_id, self.merge_request_info['source_branch'],
                ),
            ),
            Ok({'commit': _commit(commit_id=rewritten_sha, status='success')}),
            from_state='passed'
        )
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/{iid}/merge'.format(iid=self.merge_request_info['iid']),
                dict(sha=rewritten_sha, should_remove_source_branch=True, merge_when_pipeline_succeeds=True),
            ),
            Ok({}),
            from_state=['passed', 'skipped'], to_state='merged',
        )
        api.add_merge_request(dict(self.merge_request_info, state='merged'), from_state='merged')
        api.add_transition(
            GET('/projects/1234/repository/branches/{}'.format(self.merge_request_info['target_branch'])),
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

    def push_updated(self, remote_url, remote_branch, old_sha, new_sha):
        source_project = self.forked_project_info or self.project_info
        assert remote_url == source_project['ssh_url_to_repo']
        assert remote_branch == self.merge_request_info['source_branch']
        assert old_sha == INITIAL_MR_SHA
        assert new_sha == self.rewritten_sha
        self.api.state = 'pushed'

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


class TestUpdateAndAccept:  # pylint: disable=too-many-public-methods
    Mocks = namedtuple('Mocks', 'mocklab api job')

    @pytest.fixture(params=[True, False])
    def fork(self, request):
        return request.param

    @pytest.fixture(params=list(Fusion))
    def fusion(self, request):
        return request.param

    @pytest.fixture(params=[True, False])
    def add_tested(self, request):
        return request.param

    @pytest.fixture(params=[True, False])
    def add_part_of(self, request):
        return request.param

    @pytest.fixture(params=[False])  # TODO: Needs support in mocklab
    def add_reviewers(self, request):
        return request.param

    @pytest.fixture()
    def options_factory(self, fusion, add_tested, add_reviewers, add_part_of):
        def make_options(**kwargs):
            fixture_opts = {
                'fusion': fusion,
                'add_tested': add_tested,
                'add_part_of': add_part_of,
                'add_reviewers': add_reviewers,
            }
            assert not set(fixture_opts).intersection(kwargs)
            kwargs.update(fixture_opts)
            return marge.job.MergeJobOptions.default(**kwargs)
        yield make_options

    @pytest.fixture()
    def update_sha(self, fusion):
        def new_sha(new, old):
            pats = {
                marge.job.Fusion.rebase: 'rebase(%s onto %s)',
                marge.job.Fusion.merge: 'merge(%s with %s)',
                marge.job.Fusion.gitlab_rebase: 'rebase(%s onto %s)',
            }
            return pats[fusion] % (new, old)
        yield new_sha

    @pytest.fixture()
    def rewrite_sha(self, fusion, add_tested, add_reviewers, add_part_of):
        def new_sha(sha):
            # NB. The order matches the one used in the Git mock to run filters
            if add_tested and fusion == marge.job.Fusion.rebase:
                sha = 'add-tested-by(%s)' % sha

            if add_reviewers and fusion != marge.job.Fusion.gitlab_rebase:
                sha = 'add-reviewed-by(%s)' % sha

            if add_part_of and fusion != marge.job.Fusion.gitlab_rebase:
                sha = 'add-part-of(%s)' % sha

            return sha
        yield new_sha

    @pytest.fixture(autouse=True)
    def patch_sleep(self):
        with patch('time.sleep'):
            yield

    @pytest.fixture()
    def mocklab_factory(self, fork, fusion):
        expect_rebase = fusion is Fusion.gitlab_rebase
        return partial(SingleJobMockLab, fork=fork, expect_gitlab_rebase=expect_rebase)

    @pytest.fixture()
    def mocks_factory(self, mocklab_factory, options_factory, update_sha, rewrite_sha):
        # pylint: disable=too-many-locals
        def make_mocks(
            initial_master_sha=None, rewritten_sha=None,
            extra_opts=None, extra_mocklab_opts=None,
            on_push=None
        ):
            options = options_factory(**(extra_opts or {}))
            initial_master_sha = initial_master_sha or'505050505e'

            if not rewritten_sha:
                rewritten_sha = rewrite_sha(update_sha(INITIAL_MR_SHA, initial_master_sha))

            mocklab = mocklab_factory(
                initial_master_sha=initial_master_sha,
                rewritten_sha=rewritten_sha,
                **(extra_mocklab_opts or {})
            )
            api = mocklab.api

            project_id = mocklab.project_info['id']
            merge_request_iid = mocklab.merge_request_info['iid']

            project = marge.project.Project.fetch_by_id(project_id, api)
            forked_project = None
            if mocklab.forked_project_info:
                forked_project_id = mocklab.forked_project_info['id']
                forked_project = marge.project.Project.fetch_by_id(forked_project_id, api)

            merge_request = MergeRequest.fetch_by_iid(project_id, merge_request_iid, api)

            def assert_can_push(*_args, **_kwargs):
                assert options.fusion is not Fusion.gitlab_rebase

            callback = on_push or mocklab.push_updated
            repo = RepoMock.init_for_merge_request(
                merge_request=merge_request,
                initial_target_sha=mocklab.initial_master_sha,
                project=project,
                forked_project=forked_project,
            )
            repo.mock_impl.on_push_callbacks.append(assert_can_push)
            repo.mock_impl.on_push_callbacks.append(callback)

            user = marge.user.User.myself(api)
            job = marge.single_merge_job.SingleMergeJob(
                api=api, user=user,
                project=project, merge_request=merge_request, repo=repo,
                options=options,
            )
            return self.Mocks(mocklab=mocklab, api=api, job=job)

        yield make_mocks

    @pytest.fixture()
    def mocks(self, mocks_factory):
        yield mocks_factory()

    def test_succeeds_first_time(self, mocks):
        _, api, job = mocks
        job.execute()
        assert api.state == 'merged'
        assert api.notes == []

    def test_succeeds_with_updated_branch(self, mocks):
        mocklab, api, job = mocks
        api.add_transition(
            GET(
                '/projects/1234/repository/branches/{source}'.format(
                    source=mocklab.merge_request_info['source_branch'],
                ),
            ),
            Ok({'commit': {'id': mocklab.rewritten_sha}}),
            from_state='initial', to_state='pushed',
        )
        job.execute()

        assert api.state == 'merged'
        assert api.notes == []

    def test_succeeds_if_skipped(self, mocks):
        mocklab, api, job = mocks
        api.add_pipelines(
            mocklab.merge_request_info['source_project_id'],
            _pipeline(sha1=mocklab.rewritten_sha, status='running'),
            from_state='pushed', to_state='skipped',
        )
        api.add_pipelines(
            mocklab.merge_request_info['source_project_id'],
            _pipeline(sha1=mocklab.rewritten_sha, status='skipped'),
            from_state=['skipped', 'merged'],
        )
        job.execute()

        assert api.state == 'merged'
        assert api.notes == []

    def test_succeeds_if_source_is_master(self, mocks_factory):
        mocklab, api, job = mocks_factory(
            extra_mocklab_opts=dict(merge_request_options={
                'source_branch': 'master',
                'target_branch': 'production',
            }),
        )
        api.add_transition(
            GET(
                '/projects/1234/repository/branches/{source}'.format(
                    source=mocklab.merge_request_info['source_branch'],
                ),
            ),
            Ok({'commit': {'id': mocklab.rewritten_sha}}),
            from_state='initial', to_state='pushed',
        )
        job.execute()

        assert api.state == 'merged'
        assert api.notes == []

    def test_fails_if_ci_fails(self, mocks):
        mocklab, api, job = mocks
        api.add_pipelines(
            mocklab.merge_request_info['source_project_id'],
            _pipeline(sha1=mocklab.rewritten_sha, status='running'),
            from_state='pushed', to_state='failed',
        )
        api.add_pipelines(
            mocklab.merge_request_info['source_project_id'],
            _pipeline(sha1=mocklab.rewritten_sha, status='failed'),
            from_state=['failed'],
        )

        with mocklab.expected_failure("CI failed!"):
            job.execute()

        assert api.state == 'failed'

    def test_fails_if_ci_canceled(self, mocks):
        mocklab, api, job = mocks
        api.add_pipelines(
            mocklab.merge_request_info['source_project_id'],
            _pipeline(sha1=mocklab.rewritten_sha, status='running'),
            from_state='pushed', to_state='canceled',
        )
        api.add_pipelines(
            mocklab.merge_request_info['source_project_id'],
            _pipeline(sha1=mocklab.rewritten_sha, status='canceled'),
            from_state=['canceled'],
        )

        with mocklab.expected_failure("Someone canceled the CI."):
            job.execute()

        assert api.state == 'canceled'

    def test_fails_on_not_acceptable_if_master_did_not_move(self, mocks):
        mocklab, api, job = mocks
        new_branch_head_sha = '99ba110035'
        api.add_transition(
            GET(
                '/projects/{source_project_id}/repository/branches/useless_new_feature'.format(
                    source_project_id=mocklab.merge_request_info['source_project_id'],
                ),
            ),
            Ok({'commit': _commit(commit_id=new_branch_head_sha, status='success')}),
            from_state='pushed', to_state='pushed_but_head_changed'
        )
        with mocklab.expected_failure("Someone pushed to branch while we were trying to merge"):
            job.execute()

        assert api.state == 'pushed_but_head_changed'
        assert api.notes == [
            "I couldn't merge this branch: Someone pushed to branch while we were trying to merge",
        ]

    def test_fails_if_branch_is_protected(self, mocks_factory, fusion):
        def reject_push(*_args, **_kwargs):
            raise marge.git.GitError()

        mocklab, api, job = mocks_factory(on_push=reject_push)
        api.add_transition(
            GET(
                '/projects/{source_project_id}/repository/branches/useless_new_feature'.format(
                    source_project_id=mocklab.merge_request_info['source_project_id'],
                ),
            ),
            Ok(_branch('useless_new_feature', protected=True)),
            from_state='initial', to_state='protected'
        )

        if fusion is Fusion.gitlab_rebase:
            api.add_transition(
                PUT(
                    '/projects/{project_id}/merge_requests/{iid}/rebase'.format(
                        project_id=mocklab.merge_request_info['project_id'],
                        iid=mocklab.merge_request_info['iid'],
                    ),
                ),
                Error(marge.gitlab.MethodNotAllowed(405, {'message': '405 Method Not Allowed'})),
                from_state='initial',
            )

        with mocklab.expected_failure("Sorry, I can't modify protected branches!"):
            job.execute()

        assert api.state == 'protected'

    def test_second_time_if_master_moved(self, mocks_factory, fusion, update_sha, rewrite_sha):
        initial_master_sha = 'eaeaea9e9e'
        moved_master_sha = 'fafafa'
        first_rewritten_sha = rewrite_sha(update_sha(INITIAL_MR_SHA, initial_master_sha))
        second_rewritten_sha = rewrite_sha(update_sha(first_rewritten_sha, moved_master_sha))

        # pylint: disable=unused-argument
        def push_effects(remote_url, remote_branch, old_sha, new_sha):
            nonlocal mocklab, target_branch, remote_target_repo

            if api.state == 'initial':
                assert old_sha == INITIAL_MR_SHA
                assert new_sha == first_rewritten_sha
                api.state = 'pushed_but_master_moved'
                remote_target_repo.set_ref(target_branch, moved_master_sha)
            elif api.state == 'merge_rejected':
                assert new_sha == second_rewritten_sha
                api.state = 'pushed'

        mocklab, api, job = mocks_factory(
            initial_master_sha=initial_master_sha,
            rewritten_sha=second_rewritten_sha,
            on_push=push_effects,
        )

        source_project_info = mocklab.forked_project_info or mocklab.project_info
        target_project_info = mocklab.project_info

        source_project_url = source_project_info['ssh_url_to_repo']
        target_project_url = target_project_info['ssh_url_to_repo']

        source_branch = mocklab.merge_request_info['source_branch']
        target_branch = mocklab.merge_request_info['target_branch']

        remote_source_repo = job.repo.mock_impl.remote_repos[source_project_url]
        remote_target_repo = job.repo.mock_impl.remote_repos[target_project_url]

        api.add_merge_request(
            dict(
                mocklab.merge_request_info,
                sha=first_rewritten_sha,
            ),
            from_state=['pushed_but_master_moved', 'merge_rejected'],
        )
        api.add_pipelines(
            mocklab.merge_request_info['source_project_id'],
            _pipeline(sha1=first_rewritten_sha, status='success'),
            from_state=['pushed_but_master_moved', 'merge_rejected'],
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
                    source_project_id=mocklab.merge_request_info['source_project_id'],
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
        if fusion is Fusion.gitlab_rebase:
            rebase_url = '/projects/{project_id}/merge_requests/{iid}/rebase'.format(
                project_id=mocklab.merge_request_info['project_id'],
                iid=mocklab.merge_request_info['iid'],
            )

            api.add_transition(
                PUT(rebase_url), Ok(True),
                from_state='initial', to_state='pushed_but_master_moved',
                side_effect=lambda: (
                    remote_source_repo.set_ref(source_branch, first_rewritten_sha),
                    remote_target_repo.set_ref(target_branch, moved_master_sha)
                )
            )
            api.add_transition(
                PUT(rebase_url), Ok(True),
                from_state='merge_rejected', to_state='rebase-in-progress',
                side_effect=lambda: remote_source_repo.set_ref(source_branch, second_rewritten_sha)
            )

        job.execute()
        assert api.state == 'merged'
        assert api.notes == [
            "My job would be easier if people didn't jump the queue and push directly... *sigh*",
        ]

    def test_handles_races_for_merging(self, mocks):
        mocklab, api, job = mocks
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
        job.execute()
        assert api.state == 'someone_else_merged'
        assert api.notes == []

    def test_handles_request_becoming_wip_after_push(self, mocks):
        mocklab, api, job = mocks
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
        with mocklab.expected_failure(message):
            job.execute()
        assert api.state == 'now_is_wip'
        assert api.notes == ["I couldn't merge this branch: %s" % message]

    def test_guesses_git_hook_error_on_merge_refusal(self, mocks):
        mocklab, api, job = mocks
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
        with mocklab.expected_failure(message):
            job.execute()
        assert api.state == 'rejected_by_git_hook'
        assert api.notes == ["I couldn't merge this branch: %s" % message]

    def test_assumes_unresolved_discussions_on_merge_refusal(self, mocks):
        mocklab, api, job = mocks
        rewritten_sha = mocklab.rewritten_sha
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/{iid}/merge'.format(iid=mocklab.merge_request_info['iid']),
                dict(sha=rewritten_sha, should_remove_source_branch=True, merge_when_pipeline_succeeds=True),
            ),
            Error(marge.gitlab.MethodNotAllowed(405, {'message': '405 Method Not Allowed'})),
            from_state='passed', to_state='unresolved_discussions',
        )
        api.add_merge_request(
            dict(mocklab.merge_request_info),
            from_state='unresolved_discussions',
        )
        message = (
            "Gitlab refused to merge this request and I don't know why! "
            "Maybe you have unresolved discussions?"
        )
        with mocklab.expected_failure(message):
            with patch.dict(mocklab.project_info, only_allow_merge_if_all_discussions_are_resolved=True):
                job.execute()
        assert api.state == 'unresolved_discussions'
        assert api.notes == ["I couldn't merge this branch: %s" % message]

    def test_discovers_if_someone_closed_the_merge_request(self, mocks):
        mocklab, api, job = mocks
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
        with mocklab.expected_failure(message):
            job.execute()
        assert api.state == 'oops_someone_closed_it'
        assert api.notes == ["I couldn't merge this branch: %s" % message]

    def test_tells_explicitly_that_gitlab_refused_to_merge(self, mocks):
        mocklab, api, job = mocks
        rewritten_sha = mocklab.rewritten_sha
        api.add_transition(
            PUT(
                '/projects/1234/merge_requests/{iid}/merge'.format(iid=mocklab.merge_request_info['iid']),
                dict(sha=rewritten_sha, should_remove_source_branch=True, merge_when_pipeline_succeeds=True),
            ),
            Error(marge.gitlab.MethodNotAllowed(405, {'message': '405 Method Not Allowed'})),
            from_state='passed', to_state='rejected_for_mysterious_reasons',
        )
        message = "GitLab refused to merge this request and I don't know why!"
        with mocklab.expected_failure(message):
            job.execute()
        assert api.state == 'rejected_for_mysterious_reasons'
        assert api.notes == ["I couldn't merge this branch: %s" % message]

    def test_wont_merge_wip_stuff(self, mocks):
        mocklab, api, job = mocks
        wip_merge_request = dict(mocklab.merge_request_info, work_in_progress=True)
        api.add_merge_request(wip_merge_request, from_state='initial')

        with mocklab.expected_failure("Sorry, I can't merge requests marked as Work-In-Progress!"):
            job.execute()

        assert api.state == 'initial'
        assert api.notes == [
            "I couldn't merge this branch: Sorry, I can't merge requests marked as Work-In-Progress!",
        ]

    def test_wont_merge_branches_with_autosquash_if_rewriting(self, mocks):
        mocklab, api, job = mocks

        autosquash_merge_request = dict(mocklab.merge_request_info, squash=True)
        api.add_merge_request(autosquash_merge_request, from_state='initial')

        admin_user = dict(mocklab.user_info, is_admin=True)
        api.add_user(admin_user, is_current=True)

        if job.opts.requests_commit_tagging:
            message = "Sorry, merging requests marked as auto-squash would ruin my commit tagging!"
            with mocklab.expected_failure(message):
                job.execute()
            assert api.state == 'initial'
        else:
            job.execute()
            assert api.state == 'merged'

    @patch('marge.job.log', autospec=True)
    def test_waits_for_approvals(self, mock_log, mocks_factory):
        five_secs = timedelta(seconds=5)
        _, api, job = mocks_factory(
            extra_opts=dict(approval_timeout=five_secs, reapprove=True)
        )
        job.execute()

        mock_log.info.assert_any_call('Checking if approvals have reset')
        mock_log.debug.assert_any_call('Approvals haven\'t reset yet, sleeping for %s secs', ANY)
        assert api.state == 'merged'

    def test_fails_if_changes_already_exist(self, mocks):
        mocklab, api, job = mocks

        source_project_info = mocklab.forked_project_info or mocklab.project_info
        source_project_url = source_project_info['ssh_url_to_repo']
        target_project_url = mocklab.project_info['ssh_url_to_repo']
        remote_source_repo = job.repo.mock_impl.remote_repos[source_project_url]
        remote_target_repo = job.repo.mock_impl.remote_repos[target_project_url]
        source_branch = mocklab.merge_request_info['source_branch']
        target_branch = mocklab.merge_request_info['target_branch']

        remote_target_repo.set_ref(target_branch, remote_source_repo.get_ref(source_branch))
        expected_message = 'These changes already exist in branch `%s`.' % target_branch

        with mocklab.expected_failure(expected_message):
            job.execute()

        assert api.state == 'initial'
        assert api.notes == ["I couldn't merge this branch: {}".format(expected_message)]
