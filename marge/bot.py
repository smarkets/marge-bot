import logging as log
import time
from datetime import datetime, timedelta
from functools import wraps
from tempfile import TemporaryDirectory

from . import git
from . import gitlab
from . import merge_request as merge_request_module
from . import project as project_module

MergeRequest = merge_request_module.MergeRequest
Project = project_module.Project

GET, POST, PUT = gitlab.GET, gitlab.POST, gitlab.PUT


def connect_if_needed(method):
    @wraps(method)
    def wrapper(*args, **kwargs):
        self = args[0]
        if not self.connected:
            self.connect()
        return method(*args, **kwargs)

    return wrapper



def _get_id(json):
    return json['id']


class Bot(object):
    def __init__(self, *, api, user_name, project, ssh_key_file=None):
        assert project.merge_requests_enabled
        assert project.only_allow_merge_if_build_succeeds

        self._user_name = user_name
        self._ssh_key_file = ssh_key_file
        self.max_ci_waiting_time = timedelta(minutes=10)

        self.embargo_intervals = []

        self._api = api
        self._user_id = None
        self._project = project

    @property
    def connected(self):
        return self._user_id is not None

    def connect(self):
        self._user_id = self.get_my_user_id()
        assert self._user_id, "Couldn't find user id"

    @connect_if_needed
    def start(self):
        while True:
            try:
                with TemporaryDirectory() as local_repo_dir:
                    repo_url = self._project.ssh_url_to_repo
                    repo = git.Repo(repo_url, local_repo_dir, ssh_key_file=self._ssh_key_file)
                    repo.clone()
                    repo.config_user_info(
                        user_email='%s@is.a.bot' % self._user_name,
                        user_name=self._user_name,
                    )

                    self._run(repo)
            except git.GitError:
                log.error('Repository is in an inconsistent state...')

                sleep_time_in_secs = 60
                log.warning('Sleeping for %s seconds before restarting', sleep_time_in_secs)
                time.sleep(sleep_time_in_secs)

    @connect_if_needed
    def _run(self, repo):
        while True:
            log.info('Fetching merge requests assigned to me...')
            all_merge_requests = MergeRequest.fetch_all_opened(self._project.id, self._api)
            my_merge_requests = [mr for mr in all_merge_requests if mr.assignee == self._user_id]

            log.info('Got %s requests to merge', len(my_merge_requests))
            for merge_request in my_merge_requests:
                merge_request.refetch_info()
                self.process_merge_request(merge_request, repo)

            time_to_sleep_in_secs = 60
            log.info('Sleeping for %s seconds...', time_to_sleep_in_secs)
            time.sleep(time_to_sleep_in_secs)

    def during_merge_embargo(self):
        now = datetime.utcnow()
        return any(interval.covers(now) for interval in self.embargo_intervals)

    def process_merge_request(self, merge_request, repo):
        log.info('Processing !%s - %r', merge_request.iid, merge_request.title)

        if self._user_id != merge_request.assignee_id:
            log.info('It is not assigned to us anymore! -- SKIPPING')
            return

        state = merge_request.state
        if state not in ('opened', 'reopened'):
            if state in ('merged', 'closed'):
                log.info('The merge request is already %s!', state)
            else:
                log.info('The merge request is an unknown state: %r', state)
                merge_request.comment('The merge request seems to be in a weird state: %r!', state)
            merge_request.unassign()
            return

        try:
            project_id = merge_request.project_id
            source_project_id = merge_request.source_project_id
            target_project_id = merge_request.target_project_id

            if not project_id == source_project_id == target_project_id:
                raise CannotMerge("I don't yet know how to handle merge requests from different projects")

            if self.during_merge_embargo():
                log.info('Merge embargo! -- SKIPPING')
                return

            self.rebase_and_accept_merge_request(merge_request, repo)
            log.info('Successfully merged !%s.', merge_request.info['iid'])
        except CannotMerge as err:
            message = "I couldn't merge this branch: %s" % err.reason
            log.warning(message)
            merge_request.unassign()
            merge_request.comment(message)
        except git.GitError as err:
            log.exception(err)
            merge_request.comment('Something seems broken on my local git repo; check my logs!')
            raise
        except Exception as err:
            log.exception(err)
            merge_request.comment("I'm broken on the inside, please somebody fix me... :cry:")
            raise

    def rebase_and_accept_merge_request(self, merge_request, repo):
        previous_sha = merge_request.sha
        no_failure = object()
        last_failure = no_failure
        merged = False

        while not merged:
            # NB. this will be a no-op if there is nothing to rebase
            actual_sha = push_rebased_version(
                repo, merge_request.source_branch, merge_request.target_branch
            )
            if last_failure != no_failure:
                if actual_sha == previous_sha:
                    raise CannotMerge('merge request was rejected by GitLab: %r' % last_failure)

            log.info('Commit id to merge %r', actual_sha)
            time.sleep(5)

            self.wait_for_ci_to_pass(actual_sha)
            log.info('CI passed!')
            time.sleep(2)

            try:
                merge_request.accept(remove_branch=True, sha=actual_sha)
            except gitlab.NotAcceptable as err:
                log.info('Not acceptable! -- %s', err.error_message)
                last_failure = err.error_message
                previous_sha = actual_sha
            except gitlab.Unauthorized:
                log.warning('Unauthorized!')
                raise CannotMerge('My user cannot accept merge requests!')
            except gitlab.ApiError as err:
                log.exception(err)
                raise CannotMerge('had some issue with gitlab, check my logs...')
            else:
                self.wait_for_branch_to_be_merged(merge_request)
                merged = True

        if last_failure != no_failure:
            merge_request.comment(
                "My job would be easier if people didn't jump the queue and pushed directly... *sigh*"
            )


    @connect_if_needed
    def wait_for_branch_to_be_merged(self, merge_request):
        time_0 = datetime.utcnow()
        waiting_time_in_secs = 10

        while datetime.utcnow() - time_0 < self.max_ci_waiting_time:
            merge_request.refetch_info()

            if merge_request.state == 'merged':
                return  # success!
            if merge_request.state == 'closed':
                raise CannotMerge('someone closed the merge request while merging!')
            assert merge_request.state in ('opened', 'reopened'), merge_request.state

            log.info('Giving %s more secs for !%s to be merged...', waiting_time_in_secs, merge_request.iid)
            time.sleep(waiting_time_in_secs)

        raise CannotMerge('It is taking too long to see the request marked as merged!')

    @connect_if_needed
    def wait_for_ci_to_pass(self, commit_sha):
        time_0 = datetime.utcnow()
        waiting_time_in_secs = 10

        while datetime.utcnow() - time_0 < self.max_ci_waiting_time:
            ci_status = self.fetch_commit_build_status(commit_sha)
            if ci_status == 'success':
                return

            if ci_status == 'failed':
                raise CannotMerge('CI failed!')

            if ci_status == 'canceled':
                raise CannotMerge('Someone canceled the CI')

            if ci_status not in ('pending', 'running'):
                log.warning('Suspicious build status: %r', ci_status)

            log.info('Waiting for %s secs before polling CI status again', waiting_time_in_secs)
            time.sleep(waiting_time_in_secs)

        raise CannotMerge('CI is taking too long')

    def get_my_user_id(self):
        api = self._api
        user_name = self._user_name
        return api.call(GET(
            '/users',
            {'username': user_name},
            gitlab.from_singleton_list(_get_id)
        ))

    @connect_if_needed
    def fetch_commit_build_status(self, commit_sha):
        api = self._api
        project_id = self._project.id

        return api.call(GET(
            '/projects/%s/repository/commits/%s' % (project_id, commit_sha),
            extract=lambda commit: commit['status'],
        ))


class CannotMerge(Exception):
    @property
    def reason(self):
        args = self.args
        if len(args) == 0:
            return 'Unknown reason!'

        return args[0]


def push_rebased_version(repo, source_branch, target_branch):
    if source_branch == target_branch:
        raise CannotMerge('source and target branch seem to coincide!')

    branch_rebased, changes_pushed = False, False
    sha = None
    try:
        repo.rebase(branch=source_branch, new_base=target_branch)
        branch_rebased = True

        sha = repo.get_head_commit_hash()

        repo.push_force(source_branch)
        changes_pushed = True
    except git.GitError:
        if not branch_rebased:
            raise CannotMerge('got conflicts while rebasing, your problem now...')

        if not changes_pushed:
            raise CannotMerge('failed to push rebased changes, check my logs!')

        raise
    else:
        return sha
    finally:
        # A failure to clean up probably means something is fucked with the git repo
        # and likely explains any previous failure, so it will better to just
        # raise a GitError
        repo.remove_branch(source_branch)
