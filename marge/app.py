"""
An auto-merger of merge requests for GitLab
"""

import argparse
import sys

from . import bot
from . import interval
from . import gitlab
from . import project as project_module
from . import user as user_module


def _parse_args(args):
    parser = argparse.ArgumentParser(description=__doc__)
    arg = parser.add_argument
    arg(
        '--auth-token-file',
        type=argparse.FileType('rt'),
        required=True,
        metavar='FILE',
        help='',
    )
    arg(
        '--gitlab-url',
        type=str,
        required=True,
        metavar='URL',
        help='Your gitlab instance, e.g. https://gitlab.example.com',
    )
    arg(
        '--project',
        type=str,
        required=True,
        metavar='GROUP/PROJECT',
        help='foo/bar if the url is https://gitlab.example.com/foo/bar.',
    )
    arg(
        '--ssh-key-file',
        type=str,
        required=False,
        metavar='FILE',
        help='Path to the private ssh key for marge so it can clone and push'
    )
    arg(
        '--embargo',
        type=str,
        action='append',
        metavar='INTERVAL',
        default=[],
        help='Time during which no merging is to take place, e.g. "Friday 1pm - Monday 9am".',
    )
    arg(
        '--add-reviewers',
        action='store_true',
        help='add Reviewed-by: $approver for each approver of PR to each commit in PR'
    )
    arg(
        '--add-tested',
        action='store_true',
        help='add Tested: marge-bot <$PR_URL> for the final commit on branch after it passed CI',
    )
    arg(
        '--impersonate-approvers',
        action='store_true',
        help='marge pushes effectively don\'t change approval status',
    )
    arg('--debug', action='store_true', help='Debug logging (includes all HTTP requests etc.)')

    return parser.parse_args(args)


def main(args=sys.argv[1:]):
    options = _parse_args(args)

    # <https://stackoverflow.com/questions/16337511/log-all-requests-from-the-python-requests-module>
    if options.debug:
        import logging
        import http.client
        http.client.HTTPConnection.debuglevel = 2

        logging.basicConfig()
        logging.getLogger().setLevel(logging.DEBUG)
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True

    auth_token = options.auth_token_file.readline().strip()

    api = gitlab.Api(options.gitlab_url, auth_token)
    project = project_module.Project.fetch_by_path(options.project, api)
    user = user_module.User.myself(api)

    marge_bot = bot.Bot(
        api=api,
        user=user,
        project=project,
        ssh_key_file=options.ssh_key_file,
        add_reviewers=options.add_reviewers,
        add_tested=options.add_tested,
        impersonate_approvers=options.impersonate_approvers,
    )

    for embargo in options.embargo:
        marge_bot.embargo_intervals.append(interval.WeeklyInterval.from_human(embargo))

    marge_bot.start()
