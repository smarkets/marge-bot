"""
An auto-merger of merge requests for GitLab
"""

import contextlib
import logging
import os
import re
import sys
import tempfile
from datetime import timedelta

import configargparse

from . import bot
from . import interval
from . import gitlab
from . import user as user_module


class MargeBotCliArgError(Exception):
    pass


def time_interval(s):
    try:
        quant, unit = re.match(r'\A([\d.]+) ?(h|m(?:in)?|s)?\Z', s).groups()
        translate = {'h': 'hours', 'm': 'minutes', 'min': 'minutes', 's': 'seconds'}
        return timedelta(**{translate[unit or 's']: float(quant)})
    except (AttributeError, ValueError):
        raise configargparse.ArgumentTypeError('Invalid time interval (e.g. 12[s|min|h]): %s', s)


def _parse_config(args):

    def regexp(s):
        try:
            return re.compile(s)
        except re.error as err:
            raise configargparse.ArgumentTypeError('Invalid regexp: %r (%s)' % (s, err.msg))

    parser = configargparse.ArgParser(
        auto_env_var_prefix='MARGE_',
        ignore_unknown_config_file_keys=True,  # Don't parse unknown args
        config_file_parser_class=configargparse.YAMLConfigFileParser,
        formatter_class=configargparse.ArgumentDefaultsRawHelpFormatter,
        description=__doc__,
    )
    parser.add_argument(
        '--config-file',
        env_var='MARGE_CONFIG_FILE',
        type=str,
        is_config_file=True,
        help='config file path',
    )
    auth_token_group = parser.add_mutually_exclusive_group(required=True)
    auth_token_group.add_argument(
        '--auth-token',
        type=str,
        metavar='TOKEN',
        help=(
            'Your gitlab token.\n'
            'DISABLED because passing credentials on the command line is insecure:\n'
            'You can still set it via ENV variable or config file, or use "--auth-token-file" flag.\n'
        ),
    )
    auth_token_group.add_argument(
        '--auth-token-file',
        type=configargparse.FileType('rt'),
        metavar='FILE',
        help='Path to your gitlab token file.\n',
    )
    parser.add_argument(
        '--gitlab-url',
        type=str,
        required=True,
        metavar='URL',
        help='Your gitlab instance, e.g. "https://gitlab.example.com".\n',
    )
    ssh_key_group = parser.add_mutually_exclusive_group(required=True)
    ssh_key_group.add_argument(
        '--ssh-key',
        type=str,
        metavar='KEY',
        help=(
            'The private ssh key for marge so it can clone/push.\n'
            'DISABLED because passing credentials on the command line is insecure:\n'
            'You can still set it via ENV variable or config file, or use "--ssh-key-file" flag.\n'
        ),
    )
    ssh_key_group.add_argument(
        '--ssh-key-file',
        type=str,  # because we want a file location, not the content
        metavar='FILE',
        help='Path to the private ssh key for marge so it can clone/push.\n',
    )
    parser.add_argument(
        '--embargo',
        type=interval.IntervalUnion.from_human,
        metavar='INTERVAL[,..]',
        help='Time(s) during which no merging is to take place, e.g. "Friday 1pm - Monday 9am".\n',
    )
    merge_group = parser.add_mutually_exclusive_group(required=False)
    merge_group.add_argument(
        '--use-merge-strategy',
        action='store_true',
        help=(
            'Use git merge instead of git rebase\n'
            '(enable this is you use git merge as\n'
            'git tends to misbehave when both are used)\n'
        ),
    )
    merge_group.add_argument(
        '--add-tested',
        action='store_true',
        help='Add "Tested: marge-bot <$MR_URL>" for the final commit on branch after it passed CI.\n',
    )
    parser.add_argument(
        '--add-part-of',
        action='store_true',
        help='Add "Part-of: <$MR_URL>" to each commit in MR.\n',
    )
    parser.add_argument(
        '--add-reviewers',
        action='store_true',
        help='Add "Reviewed-by: $approver" for each approver of MR to each commit in MR.\n',
    )
    parser.add_argument(
        '--impersonate-approvers',
        action='store_true',
        help='Marge-bot pushes effectively don\'t change approval status.\n',
    )
    parser.add_argument(
        '--project-regexp',
        type=regexp,
        default='.*',
        help="Only process projects that match; e.g. 'some_group/.*' or '(?!exclude/me)'.\n",
    )
    parser.add_argument(
        '--ci-timeout',
        type=time_interval,
        default='15min',
        help='How long to wait for CI to pass.\n',
    )
    parser.add_argument(
        '--max-ci-time-in-minutes',
        type=int,
        default=None,
        help='Deprecated; use --ci-timeout.\n',
    )
    parser.add_argument(
        '--git-timeout',
        type=time_interval,
        default='120s',
        help='How long a single git operation can take.\n'
    )
    parser.add_argument(
        '--branch-regexp',
        type=regexp,
        default='.*',
        help='Only process MRs whose target branches match the given regular expression.\n',
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Debug logging (includes all HTTP requests etc).\n',
    )
    config = parser.parse_args(args)

    cli_args = []
    for _, (_, value) in parser._source_to_settings.get(configargparse._COMMAND_LINE_SOURCE_KEY, {}).items():
        cli_args.extend(value)
    for bad_arg in ['--auth-token', '--ssh-key']:
        if bad_arg in cli_args:
            raise MargeBotCliArgError('"%s" can only be set via ENV var or config file.' % bad_arg)
    return config


@contextlib.contextmanager
def _secret_auth_token_and_ssh_key(options):
    auth_token = options.auth_token or options.auth_token_file.readline().strip()
    if options.ssh_key_file:
        yield auth_token, options.ssh_key_file
    else:
        with tempfile.NamedTemporaryFile(mode='w', prefix='ssh-key-') as tmp_ssh_key_file:
            try:
                tmp_ssh_key_file.write(options.ssh_key + '\n')
                tmp_ssh_key_file.flush()
                yield auth_token, tmp_ssh_key_file.name
            finally:
                tmp_ssh_key_file.close()


def main(args=sys.argv[1:]):
    logging.basicConfig()

    options = _parse_config(args)

    if options.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger("requests").setLevel(logging.WARNING)

    with _secret_auth_token_and_ssh_key(options) as (auth_token, ssh_key_file):
        api = gitlab.Api(options.gitlab_url, auth_token)
        user = user_module.User.myself(api)
        if options.max_ci_time_in_minutes:
            logging.warning(
                "--max-ci-time-in-minutes is DEPRECATED, use --ci-timeout %dmin",
                options.max_ci_time_in_minutes
            )
            options.ci_timeout = timedelta(minutes=options.max_ci_time_in_minutes)

        config = bot.BotConfig(
            user=user,
            ssh_key_file=ssh_key_file,
            project_regexp=options.project_regexp,
            git_timeout=options.git_timeout,
            branch_regexp=options.branch_regexp,
            merge_opts=bot.MergeJobOptions.default(
                add_tested=options.add_tested,
                add_part_of=options.add_part_of,
                add_reviewers=options.add_reviewers,
                reapprove=options.impersonate_approvers,
                embargo=options.embargo,
                ci_timeout=options.ci_timeout,
                use_merge_strategy=options.use_merge_strategy,
            )
        )

        marge_bot = bot.Bot(api=api, config=config)
        marge_bot.start()
