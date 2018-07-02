import re
import logging as log
from collections import namedtuple

import marge.gitlab as gitlab
import tests.test_approvals as test_approvals
import tests.test_commit as test_commit
import tests.test_project as test_project
import tests.test_user as test_user

GET = gitlab.GET
POST = gitlab.POST


def commit(commit_id, status):
    return {
        'id': commit_id,
        'short_id': commit_id,
        'author_name': 'J. Bond',
        'author_email': 'jbond@mi6.gov.uk',
        'message': 'Shaken, not stirred',
        'status': status,
    }


class MockLab(object):  # pylint: disable=too-few-public-methods
    def __init__(self, gitlab_url=None):
        self.gitlab_url = gitlab_url = gitlab_url or 'http://git.example.com'
        self.api = api = Api(gitlab_url=gitlab_url, auth_token='no-token', initial_state='initial')

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


class Api(gitlab.Api):
    def __init__(self, gitlab_url, auth_token, initial_state):
        super(Api, self).__init__(gitlab_url, auth_token)

        self._transitions = {}
        self.state = initial_state
        self.notes = []

    def call(self, command, sudo=None, response_json=None):
        log.info(
            'CALL: %s%s @ %s',
            'sudo %s ' % sudo if sudo is not None else '',
            command,
            self.state,
        )
        try:
            response, next_state = self._find(command, sudo)
        except KeyError:
            page = command.args.get('page')
            if page == 0:
                no_page_args = dict((k, v) for k, v in command.args.items() if k not in ['page', 'per_page'])
                try:
                    return self.call(command._replace(args=no_page_args))
                except MockedEndpointNotFound:
                    pass  # raise the right exception below
            elif page:  # page is not None
                try:
                    # only return an empty list if the command exists
                    self.call(command.for_page(0))
                except MockedEndpointNotFound:
                    pass  # raise the right exception below
                else:
                    return []

            raise MockedEndpointNotFound(command, sudo, self.state)
        else:
            if next_state:
                self.state = next_state

            return response()

    def _find(self, command, sudo):
        more_specific = self._transitions.get(_key(command, sudo, self.state))
        return more_specific or self._transitions[_key(command, sudo, None)]

    def add_transition(self, command, response, sudo=None, from_state=None, to_state=None):
        from_states = from_state if isinstance(from_state, list) else [from_state]

        for _from_state in from_states:
            show_from = '*' if _from_state is None else repr(_from_state)
            log.info(
                'REGISTERING %s%s from %s to %s',
                'sudo %s ' % sudo if sudo is not None else '',
                command,
                show_from,
                show_from if to_state is None else repr(to_state),
            )
            self._transitions[_key(command, sudo, _from_state)] = (response, to_state)

    def add_resource(self, path, info, sudo=None, from_state=None, to_state=None, result=None):
        if result is None:
            self.add_transition(GET(path.format(attrs(info))), Ok(info), sudo, from_state, to_state)
        else:
            self.add_transition(GET(path.format(attrs(info))), Ok(result), sudo, from_state, to_state)

    def add_user(self, info, is_current=False, sudo=None, from_state=None, to_state=None):
        self.add_resource('/users/{0.id}', info, sudo, from_state, to_state)
        if is_current:
            self.add_resource('/user', info, sudo, from_state, to_state)

    def add_project(self, info, sudo=None, from_state=None, to_state=None):
        self.add_resource('/projects/{0.id}', info, sudo, from_state, to_state)
        self.add_transition(
            GET('/projects/{0.id}/merge_requests'.format(attrs(info))),
            List(r'/projects/\d+/merge_requests/\d+$', self),
            sudo, from_state, to_state,
        )

    def add_merge_request(self, info, sudo=None, from_state=None, to_state=None):
        self.add_resource('/projects/{0.project_id}/merge_requests/{0.iid}', info, sudo, from_state, to_state)

    def add_commit(self, project_id, info, sudo=None, from_state=None, to_state=None):
        path = '/projects/%s/repository/commits/{0.id}' % project_id
        self.add_resource(path, info, sudo, from_state, to_state)

    def add_approvals(self, info, sudo=None, from_state=None, to_state=None):
        path = '/projects/{0.project_id}/merge_requests/{0.iid}/approvals'
        self.add_resource(path, info, sudo, from_state, to_state)

    def add_pipelines(self, project_id, info, sudo=None, from_state=None, to_state=None):
        self.add_transition(
            GET(
                '/projects/%s/pipelines' % project_id,
                args={'ref': info['ref'], 'order_by': 'id', 'sort': 'desc'},
            ),
            Ok([info]),
            sudo, from_state, to_state,
        )
        path = '/projects/%s/pipelines/{0.id}/jobs' % project_id
        self.add_resource(path, info, sudo, None, None, result=info['jobs'])

    def expected_note(self, merge_request, note, sudo=None, from_state=None, to_state=None):
        self.add_transition(
            POST(
                '/projects/{0.project_id}/merge_requests/{0.iid}/notes'.format(attrs(merge_request)),
                args={'body': note}
            ),
            LeaveNote(note, self),
            sudo, from_state, to_state,
        )


def _key(command, sudo, state):
    return command._replace(args=frozenset(command.args.items())), sudo, state


class Ok(namedtuple('Ok', 'result')):
    def __call__(self):
        return self.result


class Error(namedtuple('Error', 'exc')):
    def __call__(self):
        raise self.exc


class List(namedtuple('List', 'prefix api')):
    def _call__(self):
        candidates = (
            command for command, _ in self.api._transitions.keys()  # pylint: disable=protected-access
            if isinstance(command, GET) and re.match(self.prefix, command.endpoint)
        )

        results = []
        for command in candidates:
            try:
                results.append(self.api.call(command))
            except MockedEndpointNotFound:
                pass

        return results


class LeaveNote(namedtuple('LeaveNote', 'note api')):
    def __call__(self):
        self.api.notes.append(self.note)
        return {}


class MockedEndpointNotFound(Exception):
    pass


def attrs(_dict):
    return namedtuple('Attrs', _dict.keys())(*_dict.values())
