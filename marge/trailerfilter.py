#!/usr/bin/env python3
"""Executable script to pass to git filter-branch --msgfilter to rewrite trailers."""
import collections
import os
import re
import sys


def drop_trailing_newlines(lines):
    while not lines[-1]:
        del lines[-1]


def remove_duplicates(trailers):
    return list(collections.OrderedDict((t, None) for t in trailers).keys())


if __name__ == '__main__':
    stdin = sys.stdin
    stdout = sys.stdout

    TRAILERS = os.getenv('TRAILERS').split('\n') if os.getenv('TRAILERS') else []
    assert all(':' in trailer for trailer in TRAILERS), TRAILERS
    TRAILER_NAMES = [trailer.split(':', 1)[0].lower() for trailer in TRAILERS]

    commit_message_lines = stdin.readlines()
    filtered_lines = [
        line.rstrip() for line in commit_message_lines
        if line.split(':', 1)[0].lower() not in TRAILER_NAMES
    ]
    reworked_lines = filtered_lines[:]

    drop_trailing_newlines(reworked_lines)
    while re.match(r'^[A-Z][\w-]+: ', reworked_lines[-1]):
        TRAILERS.insert(0, reworked_lines.pop())
    drop_trailing_newlines(reworked_lines)

    non_empty_trailers = remove_duplicates([t for t in TRAILERS if t.split(': ', 1)[1].strip()])
    if non_empty_trailers:
        reworked_lines += [''] + non_empty_trailers
    reworked_lines += ['']
    s = '\n'.join(reworked_lines)
    stdout.write(s)
