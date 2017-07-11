[![build status](https://travis-ci.org/smarkets/marge.png?branch=master)](https://travis-ci.org/smarkets/marge)

# Marge-bot

Marge-bot is a merge-bot for GitLab that, beside other goodies,
implements
[the Not Rocket Science Rule Of Software Engineering:](http://graydon2.dreamwidth.org/1597.html)

> automatically maintain a repository of code that always passes all the tests.

-- Graydon Hoare, main author of Rust

This simple rule of thumb is still nowadays surprisingly difficult to implement
with the state-of-the-art tools, and more so in a way that scales with team
size.

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


## Configuring and running

First, create a user for Marge-bot on your GitLab. We'll use `marge-bot` as
username here as well. GitLab sorts users by Name, so we recommend you pick one
that starts with a space, e.g. ` Marge Bot`, so it is quicker to assign to (our
code strips trailing whitespace in the name, so it won't show up elsewhere).
Then add `marge-bot` to your projects as `Developer` or `Master`, the latter
being required if she will merge to protected branches.

For certain features, namely, `--impersonate-approvers`, and
`--add-reviewed-by`, you will need to grant `marge-bot` admin privileges as
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
docker run
  -e MARGE_AUTH_TOKEN="$(cat marge-bot.token)" \
  -e MARGE_SSH_KEY="$(cat marge-bot-ssh-key)" \
  smarketshq/marge-bot:0.1.0 \
  --gitlab-url='http://your.gitlab.instance.com'
```

Once running, the bot will continuously monitor all projects that have its user
as a member and will pick up any changes in membership at runtime.

For completeness sake, here's how we run marge-bot at smarkets ourselves:
```
docker run
  -e MARGE_AUTH_TOKEN="$(cat marge-bot.token)" \
  -e MARGE_SSH_KEY="$(cat marge-bot-ssh-key)" \
  smarketshq/marge-bot:0.1.0 \
  --add-tested \
  --add-reviewers \
  --impersonate-approvers
  --gitlab-url='http://your.gitlab.instance.com'
```

See below for the meaning of the additional flags.

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


## Adding Reviewed-by: and Tested: messages to commits
Marge-bot supports automated addition of the following
two [standardized git commit headers](https://www.kernel.org/doc/html/v4.11/process/submitting-patches.html#using-reported-by-tested-by-reviewed-by-suggested-by-and-fixes):
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

All existing `Reviewed-by:` tags on commits in the branch will be stripped. This
feature requires marge to run with admin privileges due to a peculiarity of the
GitLab API: only admin users can obtain email addresses of other users, even
ones explicitly declared as public (strangely this limitation is particular to
email, Skype handles etc. are visible to everyone).

If you pass `--add-tested` the final commit in a PR will be tagged with
`Tested-by: marge-bot <$MERGE_REQUEST_URL>`. This can be very useful for two
reasons:

1. Seeing where stuff "came from" in a rebase-based workflow
2. Knowing that a commit has been tested, which is e.g. important for bisection
   so you can easily and automatically `git bisect --skip` untested commits.

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

More than one embargo period can be specified. Any merge request assigned to her
during an embargo period, will be merged in only once all embargoes are over.

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
