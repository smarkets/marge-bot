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
