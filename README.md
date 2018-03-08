[![build status](https://travis-ci.org/smarkets/marge-bot.png?branch=master)](https://travis-ci.org/smarkets/marge-bot)

# Marge-bot

Marge-bot is a merge-bot for GitLab that, beside other goodies,
implements
[the Not Rocket Science Rule Of Software Engineering:](http://graydon2.dreamwidth.org/1597.html)

> automatically maintain a repository of code that always passes all the tests.

— Graydon Hoare, main author of Rust

This simple rule of thumb is still nowadays surprisingly difficult to implement
with the state-of-the-art tools, and more so in a way that scales with team size
(also see our [blog
post](https://smarketshq.com/marge-bot-for-gitlab-keeps-master-always-green-6070e9d248df)).

Take, for instance, GitHub's well-known
[pull-request workflow](https://help.github.com/categories/collaborating-with-issues-and-pull-requests).
Here, CI needs to pass on the branch before the pull request can be accepted but
after that, the branch is immediately merged (or rebased) into master. By the
time this happens, enough changes may have occurred to induce test breakage, but
this is only to be found out when the commits have already landed.

GitLab (in their [enterprise edition](https://about.gitlab.com/products/)),
offers an important improvement here with
their
[semi-linear history and fast-forward](https://docs.gitlab.com/ee/user/project/merge_requests/) merge
request methods: in both cases a merge request can only be accepted if the
resulting master branch will be effectively the same as the merge request branch
on which CI has passed. If master has changed since the tests were last ran, it
is the *user's responsibility* to rebase the changes and retry. But this just
doesn't scale: if you have, a mono-repo, a large team working on short-lived
branches, a CI pipeline that takes 5-10 minutes to complete... then the number
of times one need's to rebase-and-try-to-accept starts to become unbearable.

Marge-bot offers the simplest of workflows: when a merge-request is ready, just
assign it to its user, and let her do all the rebase-wait-retry for you. If
anything goes wrong (merge conflicts, tests that fail, etc.) she'll leave a
message on the merge-request, so you'll get notified. Marge-bot can handle an
adversarial environment where some developers prefer to merge their own changes,
so the barrier for adoption is really low.

Since she is at it, she can optionally provide some other goodies like tagging
of commits (e.g. `Reviewed-by: ...`) or preventing merges during certain hours.


## Configuring

Args that start with '--' (eg. --auth-token) can also be set in a config file (specified via --config-file). The config file uses YAML syntax and must represent a YAML 'mapping' (for details, see http://learn.getgrav.org/advanced/yaml). If an arg is specified in more than one place, then commandline values override environment variables which override config file values which override defaults.
```bash
optional arguments:
  -h, --help            show this help message and exit
  --config-file CONFIG_FILE
                        config file path   [env var: MARGE_CONFIG_FILE] (default: None)
  --auth-token TOKEN    Your GitLab token.
                        DISABLED because passing credentials on the command line is insecure:
                        You can still set it via ENV variable or config file, or use "--auth-token-file" flag.
                           [env var: MARGE_AUTH_TOKEN] (default: None)
  --auth-token-file FILE
                        Path to your GitLab token file.
                           [env var: MARGE_AUTH_TOKEN_FILE] (default: None)
  --gitlab-url URL      Your GitLab instance, e.g. "https://gitlab.example.com".
                           [env var: MARGE_GITLAB_URL] (default: None)
  --ssh-key KEY         The private ssh key for marge so it can clone/push.
                        DISABLED because passing credentials on the command line is insecure:
                        You can still set it via ENV variable or config file, or use "--ssh-key-file" flag.
                           [env var: MARGE_SSH_KEY] (default: None)
  --ssh-key-file FILE   Path to the private ssh key for marge so it can clone/push.
                           [env var: MARGE_SSH_KEY_FILE] (default: None)
  --embargo INTERVAL[,..]
                        Time(s) during which no merging is to take place, e.g. "Friday 1pm - Monday 9am".
                           [env var: MARGE_EMBARGO] (default: None)
  --use-merge-strategy  Use git merge instead of git rebase (EXPERIMENTAL)
                        Enable if you use a workflow based on merge-commits and not linear history.
                           [env var: MARGE_USE_MERGE_STRATEGY] (default: False)
  --add-tested          Add "Tested: marge-bot <$MR_URL>" for the final commit on branch after it passed CI.
                           [env var: MARGE_ADD_TESTED] (default: False)
  --add-part-of         Add "Part-of: <$MR_URL>" to each commit in MR.
                           [env var: MARGE_ADD_PART_OF] (default: False)
  --add-reviewers       Add "Reviewed-by: $approver" for each approver of MR to each commit in MR.
                           [env var: MARGE_ADD_REVIEWERS] (default: False)
  --impersonate-approvers
                        Marge-bot pushes effectively don't change approval status.
                           [env var: MARGE_IMPERSONATE_APPROVERS] (default: False)
  --approval-reset-timeout APPROVAL_RESET_TIMEOUT
                        How long to wait for approvals to reset after pushing.
                        Only useful with the "new commits remove all approvals" option in a project's settings.
                        This is to handle the potential race condition where approvals don't reset in GitLab
                        after a force push due to slow processing of the event.
  --project-regexp PROJECT_REGEXP
                        Only process projects that match; e.g. 'some_group/.*' or '(?!exclude/me)'.
                           [env var: MARGE_PROJECT_REGEXP] (default: .*)
  --ci-timeout CI_TIMEOUT
                        How long to wait for CI to pass.
                           [env var: MARGE_CI_TIMEOUT] (default: 15min)
  --max-ci-time-in-minutes MAX_CI_TIME_IN_MINUTES
                        Deprecated; use --ci-timeout.
                           [env var: MARGE_MAX_CI_TIME_IN_MINUTES] (default: None)
  --git-timeout GIT_TIMEOUT
                        How long a single git operation can take.
                           [env var: MARGE_GIT_TIMEOUT] (default: 120s)
  --branch-regexp BRANCH_REGEXP
                        Only process MRs whose target branches match the given regular expression.
                           [env var: MARGE_BRANCH_REGEXP] (default: .*)
  --debug               Debug logging (includes all HTTP requests etc).
                           [env var: MARGE_DEBUG] (default: False)
```
Here is a config file example
```yaml
add-part-of: true
add-reviewers: true
add-tested: true
# chose one way of specifying the Auth token
#auth-token: TOKEN
auth-token-file: token.FILE
branch-regexp: .*
ci-timeout: 15min
embargo: Friday 1pm - Monday 9am
git-timeout: 120s
gitlab-url: "https://gitlab.example.com"
impersonate-approvers: true
project-regexp: .*
# chose one way of specifying the SSH key
#ssh-key: KEY
ssh-key-file: token.FILE
```
For more information about configuring marge-bot see `--help`


## Running

First, create a user for Marge-bot on your GitLab. We'll use `marge-bot` as
username here as well. GitLab sorts users by Name, so we recommend you pick one
that starts with a space, e.g. ` Marge Bot`, so it is quicker to assign to (our
code strips trailing whitespace in the name, so it won't show up elsewhere).
Then add `marge-bot` to your projects as `Developer` or `Master`, the latter
being required if she will merge to protected branches.

For certain features, namely, `--impersonate-approvers`, and
`--add-reviewers`, you will need to grant `marge-bot` admin privileges as
well. In the latter, so that she can query the email of the reviewers to include
it in the commit.

Second, you need an authentication token for the `marge-bot` user. If she was
made an admin to handle approver impersonation and/or adding a reviewed-by
field, then you will need to use the **PRIVATE TOKEN** found in her `Profile
Settings`. Otherwise, you can just use a personal access token that can be
generated from `Profile Settings -> Access Tokens`. Make sure it has `api` and
`read_user` scopes. Put the token in a file, e.g. `marge-bot.token`.

Finally, create a new ssh key-pair, e.g like so

```bash
ssh-keygen -t ed25519 -C marge-bot@invalid -f marge-bot-ssh-key -P ''
```

Add the public key (`marge-bot-ssh-key.pub`) to the user's `SSH Keys` in Gitlab
and keep the private one handy.

The bot can then be started from the command line as follows (using the minimal settings):
```bash
marge.app --auth-token-file marge-bot.token \
          --gitlab-url 'http://your.gitlab.instance.com' \
          --ssh-key-file marge-bot-ssh-key
```

Alternatively, you can also pass the auth token as the environment variable
`MARGE_AUTH_TOKEN` and the **CONTENTS** of the ssh-key-file as the environment
variable `MARGE_SSH_KEY`. This is very useful for running the official docker
image we provide:

```bash
docker run \
  -e MARGE_AUTH_TOKEN="$(cat marge-bot.token)" \
  -e MARGE_SSH_KEY="$(cat marge-bot-ssh-key)" \
  smarkets/marge-bot \
  --gitlab-url='http://your.gitlab.instance.com'
```

For completeness sake, here's how we run marge-bot at smarkets ourselves:
```bash
docker run \
  -e MARGE_AUTH_TOKEN="$(cat marge-bot.token)" \
  -e MARGE_SSH_KEY="$(cat marge-bot-ssh-key)" \
  smarkets/marge-bot \
  --add-tested \
  --add-reviewers \
  --impersonate-approvers \
  --gitlab-url='http://your.gitlab.instance.com'
```

Kubernetes templating with ktmpl:
```bash
ktmpl ./deploy.yml \
--parameter APP_NAME "marge-bot" \
--parameter APP_IMAGE "smarkets/marge-bot" \
--parameter KUBE_NAMESPACE "marge-bot" \
--parameter MARGE_GITLAB_URL 'http://your.gitlab.instance.com' \
--parameter MARGE_AUTH_TOKEN "$(cat marge-bot.token)" \
--parameter MARGE_SSH_KEY "$(cat marge-bot-ssh-key)" \
--parameter REPLICA_COUNT 1 | kubectl -n=${KUBE_NAMESPACE} apply --force -f -
```

Once running, the bot will continuously monitor all projects that have its user as a member and
will pick up any changes in membership at runtime.


## Suggested worfklow
1. Alice creates a new merge request and assigns Bob and Charlie as reviewers

2. Both review the code and after all issues they raise are resolved by Alice,
   they approve the merge request and assign it to `marge-bot` for merging.

3. Marge-bot rebases the latest target branch (typically master) into the
   merge-request branch and pushes it. Once the tests have passed and there is a
   sufficient number of approvals (if a minimal approvals limit has been set on
   the project), Marge-bot will merge (or rebase, depending on project settings)
   the merge request via the GitLab API. It can also add some headers to all
   commits in the merge request as described in the next section.


## Adding Reviewed-by:, Tested: and Part-of: to commit messages

Marge-bot supports automated addition of the following
two [standardized git commit trailers](https://www.kernel.org/doc/html/v4.11/process/submitting-patches.html#using-reported-by-tested-by-reviewed-by-suggested-by-and-fixes):
`Reviewed-by` and `Tested-by`. For the latter it uses `Marge Bot
<$MERGE_REQUEST_URL>` as a slight abuse of the convention (here `Marge Bot` is
the name of the `marge-bot` user in GitLab).

If you pass `--add-reviewers` and the list of approvers is non-empty and you
have enough approvers to meet the required approver count, Marge will add a the
following header to each commit message and each reviewer as it rebases the
target branch into your PR branch:

```
Reviewed-by: A. Reviewer <a.reviewer@example.com>
```

All existing `Reviewed-by:` trailers on commits in the branch will be stripped. This
feature requires marge to run with admin privileges due to a peculiarity of the
GitLab API: only admin users can obtain email addresses of other users, even
ones explicitly declared as public (strangely this limitation is particular to
email, Skype handles etc. are visible to everyone).

If you pass `--add-tested` the final commit message in a PR will be tagged with
`Tested-by: marge-bot <$MERGE_REQUEST_URL>` trailer. This can be very useful for
two reasons:

1. Seeing where stuff "came from" in a rebase-based workflow
2. Knowing that a commit has been tested, which is e.g. important for bisection
   so you can easily and automatically `git bisect --skip` untested commits.

Additionally, by using `--add-part-of`, all commit messages will be tagged with
a `Part-of: <$MERGE_REQUEST_URL>` trailer to the merge request on which they
were merged. This is useful, for example, to go from a commit shown in `git
blame` to the merge request on which it was introduced or to easily revert a all
commits introduced by a single Merge Request when using a fast-forward/rebase
based merge workflow.

## Impersonating approvers
If you want a full audit trail, you will configure Gitlab
[require approvals](https://docs.gitlab.com/ee/user/project/merge_requests/merge_request_approvals.html#approvals-required)
for PRs and also turn on
[reset approvals on push](https://docs.gitlab.com/ee/user/project/merge_requests/merge_request_approvals.html#reset-approvals-on-push).
Unfortunately, since Marge-bot's flow is based on pushing to the source branch, this
means it will reset the approval status if the latter option is enabled.
However, if you have given Marge-bot admin privileges and turned on
`--impersonate-approvers`, she will re-approve the merge request assuming after its own
push, but by impersonating the existing approvers.

## Merge embargoes

Marge-bot can be configured not to merge during certain periods. E.g., to prevent
her from merging during weekends, add `--embargo 'Friday 6pm - Monday 9am'`.
This is useful for example if you automatically deploy from master and want to
prevent shipping late on a Friday, but still want to allow marking merge requests as
"to be merged on Monday": just assign them to `marge-bot` as any other day.

More than one embargo period can be specified, separated by commas. Any merge
request assigned to her during an embargo period, will be merged in only once all
embargoes are over.

## Restricting the list of projects marge-bot considers

By default marge-bot will work on all projects that she is a member of.
Sometimes it is useful to restrict a specific instance of marge-bot to a subset
of projects. You can specify a regexp that projects must match (anchored at the
start of the string) with `--project-regexp`.

One use-case is if you want to use different configurations (e.g.
`--add-reviewers` on one project, but not the others). A simple way of doing is
run two instances of marge-bot passing `--add-reviewers --project-regexp
project/with_reviewers` to the first instance and `--project-regexp
(?!project/with_reviewers)` to the second ones. The latter regexp is a negative
look-ahead and will match any string not starting with `project/with_reviewers`.

## Restricting the list of branches marge-bot considers

It is also possible to restrict the branches marge-bot watches for incoming
merge requests. By default, marge-bot will process MRs targetted for any branch.
You may specify a regexp that target branches must match with `--branch-regexp`.

This could be useful, if for instance, you wanted to set a regular freeze
interval on your master branches for releases. You could have one instance of
marge-bot with `--embargo "Friday 1pm - Monday 9am" --branch-regexp master` and
the other with `--branch-regexp (?!master)`. This would allow development to
continue on other branches during the embargo on master.

## Some handy git aliases

Only `git bisect run` on commits that have passed CI (requires running marge-bot with `--add-tested`):
```
git config --global alias.bisect-run-tested \
 'f() { git bisect run /bin/sh -c "if !(git log -1 --format %B | fgrep -q \"Tested-by: Marge Bot\"); then exit 125; else "$@"; fi"; }; f'
```
E.g. `git bisect-run-tested ./test-for-some-bug.sh`.

Revert a whole MR, in a rebase based workflow (requires running marge-bot with `--add-part-of`):
```
git config --global alias.mr-revs '!f() { git log --grep "^Part-of.*/""$1"">" --pretty="%H"; }; f'
git config --global alias.mr-url '!f() { git log -1 --grep "^Part-of.*/""$1"">" --pretty="%b" | grep "^Part-of.*/""$1"">"  | sed "s/.*<\\(.*\\)>/\\1/"; }; f'
git config --global alias.revert-mr '!f() { REVS=$(git mr-revs "$1"); URL="$(git mr-url "$1")";  git revert --no-commit $REVS;  git commit -m "Revert <$URL>$(echo;echo; echo "$REVS" | xargs -I% echo "This reverts commit %.")"; }; f'
```

E.g. `git revert-mr 123`. This will create a single commit reverting all commits
that are part of MR 123 with a a commit message that looks like this:

```
Revert <http://gitlab.example.com/mygropup/myproject/merge_requests/123>

This reverts commit 86a3d35d9bc12e735efbf72f3e2fb895c0158713.
This reverts commit e862330a6df463e36137664f316c18b5836a4df7.
This reverts commit 0af5b70a98858c9509c895da2a673ebdb31e20b1.
```

E.g. `git revert-mr 123`.


## Troubleshooting

Marge-bot continuously logs what she is doing, so this is a good place to look
in case of issues. In addition, by passing the `--debug` flag, additional info
such as REST requests and responses will be logged. When opening an issue,
please include a relevant section of the log, ideally ran with `--debug` enabled.

The most common source of issues is the presence of git-hooks that reject
Marge-bot as a committer. These may have been explicitly installed by someone in
your organization or they may come from the project configuration. E.g., if you
are using `Settings -> Repository -> Commit author's email`, you may need to
whitelist `marge-bot`'s email.

Some versions of GitLab are not good at reporting merge failures due to hooks
(the REST API may even claim the merge operation succeeded), you can find
this in `gitlab-rails/githost.log`, under GitLab's logs directory.
