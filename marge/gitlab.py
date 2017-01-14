import json
import requests

from collections import namedtuple


class Api(object):
    def __init__(self, gitlab_url, auth_token):
        self._auth_token = auth_token
        self._api_base_url = gitlab_url.rstrip('/') + '/api/v3'

    def call(self, command):
        method = command.method
        url = self._api_base_url + command.endpoint
        headers = {'PRIVATE-TOKEN': self._auth_token}
        r = method(url, headers=headers, **command.call_args)

        if r.status_code == 200:
            return command.extract(r.json())

        if r.status_code == 201:
            return True  # Created

        if r.status_code == 304:
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

        error = errors.get(r.status_code)
        assert error, r.status_code
        try:
            err_message =  r.json()
        except json.JSONDecodeError:
            err_message = r.reason

        raise error(err_message)

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


class GET(namedtuple('GET', 'endpoint params extract')):
    @property
    def method(self):
        return requests.get

    @property
    def call_args(self):
        return {'params': _prepare_params(self.params)}

    def for_page(self, page_no):
        params = self.params or {}
        return self._replace(params=dict(params, page=page_no, per_page=100))


class PUT(namedtuple('PUT', 'endpoint body extract')):
    @property
    def method(self):
        return requests.put

    @property
    def call_args(self):
        return {'json': self.body}


class POST(namedtuple('POST', 'endpoint body extract')):
    @property
    def method(self):
        return requests.post

    @property
    def call_args(self):
        return {'json': self.body}


def _prepare_params(params):
    def process(val):
        if isinstance(val, bool):
            return 'true' if val else 'false'
        else:
            return str(val)

    return {key: process(val) for key, val in params.items()}



class ApiError(Exception):
    @property
    def error_message(self):
        args = self.args
        if len(args) == 0:
            return None

        arg = args[0]
        if isinstance(arg, dict):
            return arg.get('message')
        else:
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
