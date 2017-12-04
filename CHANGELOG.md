  * 0.4.1:
    - Fixed bug in error handling of commit rewritting (#70 / 1438867)
    - Add --project-regexp argument to restrict to certain target branches $65.
    - Sleep less between merging requests while there are jobs pending #67.
    - Less verborragic logging when --debug is used #66.
  * 0.4.0:
    - The official docker image is now on `smarkets/marge-bot` not (`smarketshq/marge-bot`).
    - Add a --add-part-of option to tag commit messages with originating MR #48.
    - Add a --git-timeout parameter (that takes time units); also add --ci-timeout
      that deprecates --max-ci-time-in-minutes #58.
    - Re-approve immediately after push #53.
    - Always use --ssh-key-file if passed (never ssh-agent or keys from ~/.ssh) #61.
    - Fix bad LOCALE problem in official image (hardcode utf-8 everywhere) #57.
    - Don't blow up on logging bad json responses #51.
    - Grammar fix #52.
  * 0.3.2: Fix support for branches with "/" in their names #50.
  * 0.3.1: Fix start-up error when running as non-admin user #49.
  * 0.3.0:
    - Display better messages when GitLab refuses to merge #32, #33.
    - Handle auto-squash being selected #14.
    - Add `--max-ci-time-in-minutes`, with default of 15 #44.
    - Fix clean-up of `ssh-key-xxx` files #38.
    - All command line args now have an environment var equivalent #35.
  * 0.2.0:
    - Add `--project-regexp` flag, to select which projects to include/exclude.
    - Fix GitLab CE incompatibilities #30.
  * 0.1.2: Fix parsing of gitlab versions #28.
  * 0.1.1: Fix failure to take into account group permissions #19.
  * 0.1.0: Initial release.
