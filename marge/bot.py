import logging as log
import time
from datetime import datetime, timedelta
from functools import wraps
from pprint import pprint
from tempfile import TemporaryDirectory

from . import git
from . import gitlab


GET, POST, PUT = gitlab.GET, gitlab.POST, gitlab.PUT


def connect_if_needed(method):
    @wraps(method)
    def wrapper(*args, **kwargs):
        self = args[0]
        if not self.connected:
            self.connect()
        return method(*args, **kwargs)

    return wrapper


def _gitlab_response_json(json):
    return json


def _from_singleton_list(f):
    def extractor(response_list):
        assert isinstance(response_list, list), type(response_list)
        assert len(response_list) <= 1, len(response_list)
        if len(response_list) == 0:
            return None
        return f(response_list[0])

    return extractor


def _get_id(json):
    return json['id']


class Bot(object):

    def __init__(self, *, user_name, auth_token, gitlab_url, project_path, ssh_key_file=None):
        self._user_name = user_name
        self._auth_token = auth_token
        self._gitlab_url = gitlab_url
        self._project_path = project_path
        self._ssh_key_file = ssh_key_file
        self.max_ci_waiting_time = timedelta(minutes=10)

        self.embargo_intervals = []

        self._api = None
        self._user_id = None
        self._project_id = None
        self._repo_url = None

    @property
    def connected(self):
        return self._api is not None

    def connect(self):
        self._api = gitlab.Api(self._gitlab_url, self._auth_token)

        log.info('Getting user_id for %s', self._user_name)
        self._user_id = self.get_my_user_id()
        assert self._user_id, "Couldn't find user id"

        log.info('Getting project_id for %s', self._project_path)
        self._project_id = self.get_project_id()
        assert self._project_id, "Couldn't find project id"

        log.info('Getting remote repo location')
        project = self.fetch_project_info()
        self._repo_url = project['ssh_url_to_repo']

        log.info('Validating project config...')
        assert self._repo_url, self.repo_url
        if not (project['merge_requests_enabled'] and project['only_allow_merge_if_build_succeeds']):
            self._api = None
            assert False, "Project is not configured correctly: %s " % {
                'merge_requests_enabled': project['merge_requests_enabled'],
                'only_allow_merge_if_build_succeeds': project['only_allow_merge_if_build_succeeds'],
            }


    @connect_if_needed
    def start(self):
        api = self._api
        user_id = self._user_id
        project_id = self._project_id
        repo_url = self._repo_url

        while True:
            try:
                with TemporaryDirectory() as local_repo_dir:
                    repo = git.Repo(repo_url, local_repo_dir, ssh_key_file=self._ssh_key_file)
                    repo.clone()

                    self._run(repo)
            except git.GitError:
                log.error('Repository is in an inconsistent state...')

                sleep_time_in_secs = 60
                log.warning('Sleeping for %s seconds before restarting', sleep_time_in_secs)
                time.sleep(sleep_time_in_secs)

    def _run(self, repo):
        while True:
            log.info('Fetching merge requests assigned to me...')
            merge_requests = self.fetch_assigned_merge_requests()

            log.info('Got %s requests to merge' % len(merge_requests))
            for merge_request in merge_requests:
                self.process_merge_request(merge_request['id'], repo)

            time_to_sleep_in_secs = 60
            log.info('Sleeping for %s seconds...' % time_to_sleep_in_secs)
            time.sleep(time_to_sleep_in_secs)

    @connect_if_needed
    def fetch_assigned_merge_requests(self):
        api = self._api
        project_id = self._project_id
        user_id = self._user_id

        def is_merge_request_assigned_to_user(merge_request):
            assignee = merge_request.get('assignee') or {}  # NB. it can be None, so .get('assignee', {}) won't work
            return assignee.get('id') == user_id

        merge_requests = api.collect_all_pages(GET(
            '/projects/%s/merge_requests' % project_id,
            {'state': 'opened', 'order_by': 'created_at', 'sort': 'asc'},
            _gitlab_response_json,
        ))
        return [mr for mr in merge_requests if is_merge_request_assigned_to_user(mr)]

    def during_merge_embargo(self, target_branch):
        now = datetime.utcnow()
        return any(interval.covers(now) for interval in self.embargo_intervals)

    def process_merge_request(self, merge_request_id, repo):
        log.info('Processing merge request %s', merge_request_id)

        merge_request = self.fetch_merge_request_info(merge_request_id)
        log.info('!%s - %r', merge_request['iid'], merge_request['title'])

        if self._user_id != get_assignee_id(merge_request):
            log.info('It is not assigned to us anymore! -- SKIPPING')
            return

        state = merge_request['state']
        if state not in ('opened', 'reopened'):
            if state in ('merged', 'closed'):
                log.info('The merge request is already %s!', state)
            else:
                log.info('The merge request is an unknown state: %r', state)
                self.comment_on_merge_request('The merge request seems to be in a weird state: %r!', state)
            self.mark_merge_request_as_unassigned(merge_request_id)
            return

        try:
            project_id = merge_request['project_id']
            source_project_id = merge_request['source_project_id']
            target_project_id = merge_request['target_project_id']

            if not (project_id == source_project_id == target_project_id):
                raise CannotMerge("I don't yet know how to handle merge requests from different projects")

            if self.during_merge_embargo(merge_request['target_branch']):
                log.info('Merge embargo! -- SKIPPING')
                return

            try:
                # NB. this will be a no-op if there is nothing to rebase
                actual_sha = self.push_rebased_version(merge_request, repo)
                log.info('Commit id to merge %r', actual_sha)
                time.sleep(5)

                self.wait_for_ci_to_pass(actual_sha)
                log.info('CI passed!')
                time.sleep(2)

                self.accept_merge_request(merge_request['id'], repo, sha=actual_sha)
                self.wait_for_branch_to_be_merged(merge_request_id)

                log.info('Successfully merged !%s.', merge_request['iid'])
            except git.GitError as e:
                raise CannotMerge('got conflicts when rebasing or something like that')
        except CannotMerge as e:
            message = "I couldn't merge this branch: %s" % e.reason
            log.warning(message)
            self.mark_merge_request_as_unassigned(merge_request_id)
            self.comment_on_merge_request(merge_request_id, message)
            self.log_merge_request_status(merge_request_id, 'Merge request info after failing:')
        except git.GitError as e:
            log.exception(e)
            self.comment_on_merge_request(merge_request_id,
                'Something seems broken on my local git repo; check my logs!'
            )
            raise
        except Exception as e:
            log.exception(e)
            self.comment_on_merge_request(merge_request_id,
                "I'm broken on the inside, please somebody fix me... :cry:"
            )
            raise

    def push_rebased_version(self, merge_request, repo):
        source_branch = merge_request['source_branch']
        target_branch = merge_request['target_branch']

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
        except git.GitError as e:
            if not branch_rebased:
                raise CannotMerge('got conflicts while rebasing, your problem now...')

            if not changes_pushed :
                raise CannotMerge('failed to push rebased changes, check my logs!')

            raise
        else:
            return sha
        finally:
            # A failure to clean up probably means something is fucked with the git repo
            # and likely explains any previous failure, so it will better to just
            # raise a GitError
            repo.remove_branch(source_branch)

    @connect_if_needed
    def accept_merge_request(self, merge_request_id, repo, sha=None):
        api = self._api
        project_id = self._project_id

        try:
            result = api.call(PUT(
                '/projects/%s/merge_requests/%s/merge' % (project_id, merge_request_id),
                 dict(
                    should_remove_source_branch=True,
                    merge_when_build_succeeds=True,
                    sha=sha,  # if provided, ensures what is merged is what we want (or fails)
                ),
                 _gitlab_response_json,
            ))
        except gitlab.Unauthorized:
            log.warning('Unauthorized!')
            raise CannotMerge('My user cannot accept merge requests!')
        except gitlab.NotAcceptable as e:
            log.info('Not acceptable! -- %s', e.error_message)
            raise CannotMerge('gitlab rejected the merge with %r', e.error_message)
        except gitlab.ApiError as e:
            log.exception(e)
            raise CannotMerge('had some issue with gitlab, check my logs...')

    @connect_if_needed
    def wait_for_branch_to_be_merged(self, merge_request_id):
        time_0 = datetime.utcnow()
        waiting_time_in_secs = 10

        while datetime.utcnow() - time_0 < self.max_ci_waiting_time:
            merge_request = self.fetch_merge_request_info(merge_request_id)

            state = merge_request['state']
            if state == 'merged':
                return  # success!
            if state == 'closed':
                raise CannotMerge('someone closed the merge request while merging!')
            assert state == 'opened', state

            log.info('Giving %s more secs to the CI of %s...', waiting_time_in_secs, merge_request_id)
            time.sleep(waiting_time_in_secs)

        raise CannotMerge('CI is taking too long!')

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
                log.warning('Susicious build status: %r', ci_status)

            log.info('Waiting for %s secs before polling CI status again', waiting_time_in_secs)
            time.sleep(waiting_time_in_secs)

        raise CannotMerge('CI is taking too long')


    @connect_if_needed
    def mark_merge_request_as_unassigned(self, merge_request_id):
        api = self._api
        project_id = self._project_id
        return api.call(PUT(
            '/projects/%s/merge_requests/%s' % (project_id, merge_request_id),
            {'assignee_id': None},
            _gitlab_response_json,
        ))

    @connect_if_needed
    def comment_on_merge_request(self, merge_request_id, message):
        api = self._api
        project_id = self._project_id
        return api.call(POST(
            '/projects/%s/merge_requests/%s/notes' % (project_id, merge_request_id),
            {'body': message},
            _gitlab_response_json,
        ))

    @connect_if_needed
    def get_my_user_id(self):
        api = self._api
        user_name = self._user_name
        return api.call(GET(
            '/users',
            {'username': user_name},
            _from_singleton_list(_get_id)
        ))

    @connect_if_needed
    def get_project_id(self):
        api = self._api
        project_path = self._project_path

        def filter_by_path_with_namespace(projects):
            return [p for p in projects if p['path_with_namespace'] == project_path]

        return api.call(GET(
            '/projects', {},
            lambda projects: _from_singleton_list(_get_id)(filter_by_path_with_namespace(projects))
        ))

    @connect_if_needed
    def fetch_project_info(self):
        api = self._api
        project_id = self._project_id

        return api.call(GET(
            '/projects/%s' % project_id, {},
            _gitlab_response_json,
        ))

    @connect_if_needed
    def fetch_merge_request_info(self, merge_request_id, extract=_gitlab_response_json):
        api = self._api
        project_id = self._project_id

        return api.call(GET(
            '/projects/%s/merge_requests/%s' % (project_id, merge_request_id),
            {},
            extract,
        ))

    @connect_if_needed
    def fetch_commit_build_status(self, commit_sha):
        api= self._api
        project_id = self._project_id

        return api.call(GET(
            '/projects/%s/repository/commits/%s' % (project_id, commit_sha),
            {},
            lambda commit: commit['status'],
        ))

    @connect_if_needed
    def log_merge_request_status(self, merge_request_id, header=None):
        if header:
            log.info(header)

        current_status = self.fetch_merge_request_info(merge_request_id)
        log.info(pprint(current_status))


class CannotMerge(Exception):
    @property
    def reason(self):
        args = self.args
        if len(args) == 0:
            return 'Unknown reason!'

        return args[0]


def get_assignee_id(merge_request):
    assignee = merge_request['assignee'] or {}
    return assignee.get('id')
