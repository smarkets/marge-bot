"""
An auto-merger of merge requests for GitLab
"""

import argparse
import sys

from . import bot
from . import interval


def _parse_args(args):
    parser = argparse.ArgumentParser(description=__doc__)
    arg = parser.add_argument
    arg('--user', type=str, required=True)
    arg('--auth-token-file', type=argparse.FileType('rt'), required=True, metavar='FILE')
    arg('--gitlab-url', type=str, required=True, metavar='URL')
    arg('--project', type=str, required=True, metavar='GROUP/PROJECT')
    arg('--ssh-key-file', type=str, required=False, metavar='FILE')
    arg('--embargo', type=str, action='append', metavar='INTERVAL')

    return parser.parse_args(args)

def main(args=sys.argv[1:]):
    options = _parse_args(args)
    auth_token = options.auth_token_file.readline().strip()
    marge_bot = bot.Bot(
        user_name=options.user,
        auth_token=auth_token,
        gitlab_url=options.gitlab_url,
        project_path=options.project,
        ssh_key_file=options.ssh_key_file,
    )

    for embargo in options.embargo:
        marge_bot.embargo_intervals.append(interval.WeeklyInterval.from_human(embargo))

    marge_bot.start()
