[![build status](http://git.hanson.smarkets.com/hanson/marge/badges/master/build.svg)](http://git.hanson.smarkets.com/hanson/marge/commits/master)
[![coverage report](http://git.hanson.smarkets.com/hanson/marge/badges/master/coverage.svg)](http://git.hanson.smarkets.com/hanson/marge/commits/master)

# Marge does Gitlab PRs the right way

Marge implements the following for gitlab:

[The Not Rocket Science Rule Of Software Engineering:](graydon2.dreamwidth.org/1597.html)

> automatically maintain a repository of code that always passes all the tests.

-- Graydon Hoare, main author of Rust

The way github, gitlab and most PR flows work by default violates this rule and
therefore produces broken masters on a regular basis. The standard (and wrong)
approach is to run CI on the branch and if CI passes on the branch you merge (or
rebase) into master. If master has diverged in the meantime the merge will
sometimes introduce test breakage.

The correct way is to rebase (or merge) master into the feature branch, run CI
on that and if it passes rebase (or merge) into master. You can still want to
run CI on the branch as you develop it of course, but the critical thing is that
before merging you run tests on what would be the state of the master branch
*after* the merge.

Finally, marge optionally tag commits with Reviewed-by: and Tested-by: headers,
which can be very useful for auditing and bisecting, respectively.

## How Marge does it

Marge is a simple auto-merging robot for GitLab: it will regularly poll its
project for merge-requests that are assigned to her, will then rebase the
branch, push (with `--force`) to the branch, wait for CI to pass and will then
merge the request via the gitlab API (this will have the same effect as pressing
the "Merge" button in the UI, which means it will trigger a merge commit in the
default setup and a rebase).

As long as Marge is the only one merging, no conflicts will be introduced.

Marge also adds optional additional conveniences for auditing and bisecting, see
[Adding Reviewed-by: and Tested: messages to commits](#adding-reviewed-by-and-tested-messages-to-commits).

## Configuring and running

First, create a user for Marge (`marge-bot` is the suggested name) on your
gitlab and add it to your project as a developer or admin. If you want to use
certain features (`--impersonate-approvers`, `--add-reviewed-by`), you will need
to grant marge admin privileges.

Second, from the user's `Profile Settings`, download the **PRIVATE TOKEN** and
put it in a file (e.g., `marge-bot.token`). Be aware that there are other token
types one can download from the settings and they may to appear at work first to
work, but only the **PRIVATE TOKEN** provides sufficient rights to carry out all
actions that marge needs to perform (in particular `--impersonate-approvers` and
`--add-reviewed-by` do require marge-bot's private token to exercise admin
rights).

Finally, create a new ssh key-pair, e.g like so

```bash
ssh-keygen -t ed25519 -C marge-bot@example.com -f marge-bot-ssh-key -P ''
```

Add the public key (`marge-bot-ssh-key.pub`) to the user's `SSH Keys` in Gitlab
and keep the private one handy.

The bot can then be started from the command line as follows:
```bash
marge.app --auth-token-file marge-bot.token \
          --gitlab-url 'http://your.gitlab.instance.com' \
          --project group/name \
          --ssh-key-file marge-bot-ssh-key
```

## Suggested Worfklow
1. Alice creates a new merge request and assigns Bob and Charles as reviewers

2. Both review the code and after all issues they raise are resolved by Alice,
   they approve the merge request and assign it to marge-bot for merging.

3. marge-bot rebases the latest target branch (typically master) into the
   merge-request branch and pushes it. Once the tests have passed and there is a
   sufficient number of approvals (if a minimal approvals limit has been set on
   the project), marge will merge (or rebase, depending on project settings) the
   merge request via the gitlab API. It can also add some headers to all commits
   in the merge request as described in the next section.


## Adding Reviewed-by: and Tested: messages to commits
Marge supports automated addition of the following
two [standardized git commit headers](https://www.kernel.org/doc/html/v4.11/process/submitting-patches.html#using-reported-by-tested-by-reviewed-by-suggested-by-and-fixes): `Reviewed-by` and `Tested-by`. For the
latter it uses `marge-bot <$MERGE_REQUEST_URL>` as a slight abuse of the
convention.

If you pass `--add-reviewers` and the list of approvers is non-empty and you
have enough approvers to meet the required approver count, marge will add a the
following header to each commit message and each reviewer as it rebases the
target branch into your PR branch:

```
Reviewed-by: A. Reviewer <a.reviewer@example.com>
```

All existing `Reviewed-by:` tags on commits in the branch will be stripped. This
feature requires marge to run with admin privileges due to a pecularity of the
Gitlab API: only admin users can obtain email addresses of other users, even
ones explicitly declared as public (strangely this limitation is particular to
email, skype handles etc. are visible to everyone).

If you pass `--add-tested` the final commit in a PR will be tagged with
`Tested-by: marge-bot <$MERGE_REQUEST_URL>`. This can be very useful for two
reasons:

1. Seeing where stuff "came from" in a rebase-based workflow
2. Knowing that a commit has been tested, which is e.g. important for bisection
   so you can easily and automatically `git bisect --skip` untested commits.

## Impersonating approvers
If you want a full audit trail, you will configure
gitlab
[require approvals](https://docs.gitlab.com/ee/user/project/merge_requests/merge_request_approvals.html#approvals-required) for
PRs and also turn
on
[reset approvals on push]( https://docs.gitlab.com/ee/user/project/merge_requests/merge_request_approvals.html#reset-approvals-on-push).
Unfortunately, since marge's flow is based on pushing to the source branch, this
means it will reset the approval status if the latter option is enabled.
However, if you have given marge admin privileges and turned on
`--impersonate-approvers`, marge will re-approve the PR assuming after its own
push, but by impersonating the existing approvers.

## Merge embargoes

Marge can be configured not to merge during certain periods. E.g., to prevent
her from merging during weekends, add `--embargo 'Friday 6pm - Monday 9am'`.
More than one embargo period can be specified. Any merge request assigned to her
during an embargo period, will be merged in only once all embargoes are over.
