import json
from collections import namedtuple

import requests


class Api(object):
    def __init__(self, gitlab_url, auth_token):
        self._auth_token = auth_token
        self._api_base_url = gitlab_url.rstrip('/') + '/api/v3'

    def call(self, command):
        method = command.method
        url = self._api_base_url + command.endpoint
        headers = {'PRIVATE-TOKEN': self._auth_token}
        response = method(url, headers=headers, **command.call_args)

        if response.status_code == 200:
            return command.extract(response.json()) if command.extract else response.json()

        if response.status_code == 201:
            return True  # Created

        if response.status_code == 304:
            return False  # Not Modified

        errors = {
            400: BadRequest,
            401: Unauthorized,
            403: Forbidden,
            404: NotFound,
            405: MethodNotAllowed,
            406: NotAcceptable,
            409: Conflict,
            422: Unprocessable,
            500: InternalServerError,
        }

        def other_error(code, msg):
            exception = InternalServerError if 500 < code < 600 else UnexpectedError
            return exception(code, msg)

        error = errors.get(response.status_code, other_error)
        try:
            err_message = response.json()
        except json.JSONDecodeError:
            err_message = response.reason

        raise error(response.status_code, err_message)

    def collect_all_pages(self, get_command):
        result = []
        fetch_again, page_no = True, 1
        while fetch_again:
            page = self.call(get_command.for_page(page_no))
            if page:
                result.extend(page)
                page_no += 1
            else:
                fetch_again = False

        return result


def from_singleton_list(fun=None):
    fun = fun or (lambda x: x)
    def extractor(response_list):
        assert isinstance(response_list, list), type(response_list)
        assert len(response_list) <= 1, len(response_list)
        if not response_list:
            return None
        return fun(response_list[0])

    return extractor


class Command(namedtuple('Command', 'endpoint args extract')):
    def __new__(cls, endpoint, args=None, extract=None):
        return super(Command, cls).__new__(cls, endpoint, args or {}, extract)

    @property
    def call_args(self):
        return {'json': self.args}


class GET(Command):
    @property
    def method(self):
        return requests.get

    @property
    def call_args(self):
        return {'params': _prepare_params(self.args)}

    def for_page(self, page_no):
        args = self.args
        return self._replace(args=dict(args, page=page_no, per_page=100))


class PUT(Command):
    @property
    def method(self):
        return requests.put

class POST(Command):
    @property
    def method(self):
        return requests.post


def _prepare_params(params):
    def process(val):
        if isinstance(val, bool):
            return 'true' if val else 'false'
        return str(val)

    return {key: process(val) for key, val in params.items()}



class ApiError(Exception):
    @property
    def error_message(self):
        args = self.args
        if len(args) != 2:
            return None

        arg = args[1]
        if isinstance(arg, dict):
            return arg.get('message')
        return arg


class BadRequest(ApiError):
    pass


class Unauthorized(ApiError):
    pass


class Forbidden(ApiError):
    pass


class NotFound(ApiError):
    pass


class MethodNotAllowed(ApiError):
    pass


class NotAcceptable(ApiError):
    pass


class Conflict(ApiError):
    pass


class Unprocessable(ApiError):
    pass


class InternalServerError(ApiError):
    pass

class UnexpectedError(ApiError):
    pass


class Resource(object):
    def __init__(self, api, info):
        self._info = info
        self._api = api

    @property
    def info(self):
        return self._info

    @property
    def id(self):
        return self.info['id']
