"""
An auto-merger of merge requests for GitLab
"""

import argparse
import contextlib
import logging
import os
import re
import sys
import tempfile
from datetime import timedelta

from . import bot
from . import interval
from . import gitlab
from . import user as user_module


def _parse_args(args):
    parser = argparse.ArgumentParser(description=__doc__)

    def arg(name, env_var=True, **kwargs):
        if env_var:
            env_var_name = 'MARGE_' + name[2:].replace('-', '_').upper()
            env_var_val = os.getenv(env_var_name)
            if env_var_val:
                if kwargs.get('action') in ['store_true', 'store_false']:
                    env_var_val = env_var_val.lower() in ['true', 'yes', '1']
                kwargs = dict(kwargs, default=env_var_val, required=False)

        parser.add_argument(name, **kwargs)

    def regexp(s):
        try:
            return re.compile(s)
        except re.error as err:
            raise argparse.ArgumentTypeError('Invalid regexp: %r (%s)' % s, err.msg)

    arg(
        '--auth-token-file',
        type=argparse.FileType('rt'),
        metavar='FILE',
        help='Your gitlab token; must provide this flag or set MARGE_AUTH_TOKEN',
        env_var=False,
    )
    arg(
        '--gitlab-url',
        type=str,
        required=True,
        metavar='URL',
        help='Your gitlab instance, e.g. https://gitlab.example.com',
    )
    arg(
        '--ssh-key-file',
        type=str,
        metavar='FILE',
        help=(
            'Path to the private ssh key for marge so it can clone/push. '
            'Provide or set MARGE_SSH_KEY (to the *contents*)'
        ),
        env_var=False,
    )
    arg(
        '--embargo',
        type=interval.IntervalUnion.from_human,
        metavar='INTERVAL[,..]',
        help='Time(s) during which no merging is to take place, e.g. "Friday 1pm - Monday 9am".',
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
    arg(
        '--project-regexp',
        type=regexp,
        default='.*',
        help="Only process projects that match; e.g. 'some_group/.*' or '(?!exclude/me)'",
    )
    arg(
        '--max-ci-time-in-minutes',
        type=int,
        default=15,
        help='How long to wait for CI to pass.',
    )
    arg('--debug', action='store_true', help='Debug logging (includes all HTTP requests etc.)')

    return parser.parse_args(args)


@contextlib.contextmanager
def _secret_auth_token_and_ssh_key(options):
    if options.auth_token_file is None:
        auth_token = os.getenv('MARGE_AUTH_TOKEN')
        assert auth_token, "You need to pass --auth-token or set envvar MARGE_AUTH_TOKEN"
    else:
        auth_token = options.auth_token_file.readline()

    ssh_key_file = options.ssh_key_file
    if ssh_key_file:
        yield auth_token.strip(), ssh_key_file
    else:
        with tempfile.NamedTemporaryFile(mode='w', prefix='ssh-key-') as env_ssh_key_file:
            try:
                ssh_key = os.getenv('MARGE_SSH_KEY')
                assert ssh_key, "You need to pass --ssh-key-file or set envvar MARGE_SSH_KEY"
                env_ssh_key_file.write(ssh_key + '\n')
                env_ssh_key_file.flush()
                yield auth_token.strip(), env_ssh_key_file.name
            finally:
                env_ssh_key_file.close()


def main(args=sys.argv[1:]):
    logging.basicConfig()

    options = _parse_args(args)

    if options.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    with _secret_auth_token_and_ssh_key(options) as (auth_token, ssh_key_file):
        api = gitlab.Api(options.gitlab_url, auth_token)
        user = user_module.User.myself(api)

        config = bot.BotConfig(
            user=user,
            ssh_key_file=ssh_key_file,
            project_regexp=options.project_regexp,
            merge_opts=bot.MergeJobOptions.default(
                add_tested=options.add_tested,
                add_reviewers=options.add_reviewers,
                reapprove=options.impersonate_approvers,
                embargo=options.embargo,
                max_ci_waiting_time=timedelta(minutes=options.max_ci_time_in_minutes),
            )
        )

        marge_bot = bot.Bot(api=api, config=config)
        marge_bot.start()
