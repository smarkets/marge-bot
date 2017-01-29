[![build status](http://git.hanson.smarkets.com/hanson/marge/badges/master/build.svg)](http://git.hanson.smarkets.com/hanson/marge/commits/master)
[![coverage report](http://git.hanson.smarkets.com/hanson/marge/badges/master/coverage.svg)](http://git.hanson.smarkets.com/hanson/marge/commits/master)

# Marge

Marge is a simple auto-merging robot for GitLab: it will regularly poll its
project for merge-requests that are assigned to her, will then rebase the
branch, push (with `--force`) to the branch, wait for CI to pass and will then approve the request. As long as Marge is the only one merging, no conflicts will be introduced.

## Configuring and running.

First, create a user for Marge on your gitlab and add it to your project as a developer. Second, from the user's `Profile Settings`, create a new access token and put it ona file (e.g., `marge.token`). Finally, create a new ssh key-pair, add the public key to the user's `SSH Keys` and keep the private one handy.

The bot can then be started from the command line as follows:
```bash
marge.app --user <user> --auth-token-file marge.token --gitlab-url 'http://your.gitlab.instance.com' --project group/name --ssh-key-file private-key
```

## Merge embargoes

Marge can be configured not to merge during certain periods. E.g., to prevent her from merging during weekends, add `--embargo 'Friday 6pm - Monday 9am'`. 
More than one embargo period can be specified. Any merge request assigned to her during an embargo period, will be merged in only once all embargoes are over.
