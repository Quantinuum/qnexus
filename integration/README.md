# qnexus integration test suite

These tests are intended to be runnable against any Nexus environment by any user (with quotas enabled for basic Nexus usage).
The tests will login the user and create all projects/resources required, deleting them once the test suite has run.

In general we target the Nexus QA environment at https://qa.myqos.com using the
QA test user with email: 'qa_nexus_staging_pytket-nexus@mailsac.com'.

Requires the following environment variables to be set:

- NEXUS_QA_USER_EMAIL
- NEXUS_QA_USER_PASSWORD
- NEXUS_DOMAIN (to avoid targetting prod by default)
- NEXUS_QA_QSYS_DEVICE (for executing HUGR programs on a next-gen qsys device)

You can then set up the auth tokens for the NEXUS_USER_EMAIL user with:

```sh
uv run python integration/setup_tokens.py
```

And run the tests with:

```sh
uv run pytest integration/
```

## pytest custom options

The complete list can be found in the "Custom options:" section when doing `uv run pytest integration/ --help`.

### Test run identifier

The `--run-id <string>` sets an identifier that is used in the `test_case_name` fixture, which is in turn used
by the test cases in the names of the generated resources. If not provided, the `testrun_uid` value
provided by the `pytest-xdist` plugin is used.

You can use this to easily identify the resources created by a particular test run. In the CI we set
`--run-id github.run_id(github.run_attempt)`. Beware that if you provide the same identifier for multiple
runs, the tests that require unique names might fail.

### Purge projects

By default projects created during the test run will not be purged (archived and deleted). Specifying the
flag `--purge-projects` will make it so all the projects are purged immediately after a test finishes.

## Cross-region job submission tests

The `integration/cross_region` suite verifies that a job can be submitted from a "home" region to a
different "target" region (e.g. logging in against SG and submitting a job with `target_region="us"`),
and that its results can be retrieved.

This suite is skipped by default and requires the QA test user to have access to both regions. To enable
it, set:

- `NEXUS_CROSS_REGION_TESTS` (to any value, to enable the suite)
- `NEXUS_HOME_REGION` (region to log in against, defaults to `"sg"`)
- `NEXUS_TARGET_REGION` (region to target job submissions at, defaults to `"us"`)
- `NEXUS_SG_DOMAIN` / `NEXUS_US_DOMAIN` (if the region's QA domain differs from the production default)
- `NEXUS_QA_HOME_USER_EMAIL` (user with cross region access)
- `NEXUS_QA_HOME_USER_PASSWORD` (user creds with cross region access)

Device/system names used per-region are configured in `integration/cross_region/region_config.json`.
