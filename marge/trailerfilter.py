#!/usr/bin/env python3
"""Executable script to pass to git filter-branch --msgfilter to rewrite trailers.

This treats everything (stdin, stdout, env) at the level of raw bytes which are
assumed to be utf-8, or more specifically some ASCII superset, regardless of
(possibly broken) LOCALE settings.

"""
import collections
import os
import re
import sys

stdin = sys.stdin.buffer
stdout = sys.stdout.buffer
stderr = sys.stderr.buffer


def die(msg):
    stderr.write(b'ERROR: ')
    stderr.write(msg)
    sys.exit(1)


def drop_trailing_newlines(lines):
    while lines and not lines[-1]:
        del lines[-1]


def remove_duplicates(trailers):
    return list(collections.OrderedDict((t, None) for t in trailers).keys())


def rework_commit_message(commit_message, trailers):
    if not commit_message:
        die(b'Expected a non-empty commit message')

    trailer_names = [trailer.split(b':', 1)[0].lower() for trailer in trailers]

    filtered_lines = [
        line.rstrip() for line in commit_message.split(b'\n')
        if line.split(b':', 1)[0].lower() not in trailer_names
    ]

    reworked_lines = filtered_lines[:]

    drop_trailing_newlines(reworked_lines)
    while len(reworked_lines) > 1 and re.match(br'^[A-Z][\w-]+: ', reworked_lines[-1]):
        trailers.insert(0, reworked_lines.pop())
    if not reworked_lines:
        die(b"Your commit message seems to consist only of Trailers: " + original_commit_message)

    drop_trailing_newlines(reworked_lines)

    non_empty_trailers = remove_duplicates([t for t in trailers if t.split(b': ', 1)[1].strip()])
    if non_empty_trailers:
        reworked_lines += [b''] + non_empty_trailers
    reworked_lines += [b'']
    return b'\n'.join(reworked_lines)


if __name__ == '__main__':
    TRAILERS = os.environb[b'TRAILERS'].split(b'\n') if os.environb[b'TRAILERS'] else []
    assert all(b':' in trailer for trailer in TRAILERS), TRAILERS
    original_commit_message = stdin.read().strip()
    new_commit_message = rework_commit_message(original_commit_message, TRAILERS)
    stdout.write(new_commit_message)
