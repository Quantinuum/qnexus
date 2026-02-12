# qnexus



[![pypi][]](https://pypi.org/project/qnexus/)
[![py-version][]](https://pypi.org/project/qnexus/)

  [py-version]: https://img.shields.io/pypi/pyversions/qnexus
  [pypi]: https://img.shields.io/pypi/v/qnexus

A python client for the [Quantinuum Nexus](https://nexus.quantinuum.com) platform.

```python
import qnexus as qnx

# Will open a browser window to login with Nexus credentials
qnx.login()

# Dataframe representation of all your pending jobs in Nexus
qnx.jobs.get_all(job_status=["SUBMITTED", "QUEUED", "RUNNING"]).df()
```


## Install

qnexus can be installed via `pip`.

```sh
pip install qnexus
```


## Usage

Usage examples and tutorials are available [here][examples].

[examples]: ./examples/


## Development

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

The easiest way to setup the development environment is to use the provided devenv.nix file. This will setup a development shell with all the required dependencies.

To use this, you will need to install [devenv](https://devenv.sh/getting-started/). Once you have it running, open a shell with:

```bash
devenv shell
```

Specifically the project relies on these tools:

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/)
- [commitizen](https://commitizen-tools.github.io/commitizen/)
- [git](https://git-scm.com/)


### Installation for development

By default devenv will set up your `uv` virtual environment. If you aren't using devenv please check the [uv](https://docs.astral.sh/uv/) documentation for creating and using a virtual environment.

You can then install all dependencies with:

```sh
uv sync
```

To run a single command in the shell, just prefix it with `uv run`.


### Checks

Formatting, linting and type-checking are added as a devenv script and can be run with:

```sh
qfmt
```

### Testing

Most of the test suite are integration tests that require the following environment variables:

```sh
NEXUS_DOMAIN = "qa.myqos.com"
NEXUS_QA_USER_EMAIL = "qa_nexus_staging_pytket-nexus@mailsac.com"
NEXUS_QA_USER_PASSWORD = <copy from Bitwarden 'qnexus integration tests user'>
NEXUS_QA_QSYS_DEVICE = "H1-1E"
```

And can be run locally (for the above user) with:

```sh
uv run python integration/setup_tokens.py

uv run pytest integration/
```

These will only be available to run via Github CI by internal team members. For external contributions we recommend writing unit tests and/or integration tests and requesting they
be run by an internal reviewer.

Unit tests can be run with:

```sh
uv run scripts/run_unit_tests.sh
```

or to run via devenv script:

```sh
qtest
```

As some auth tests these manipulate environment variables they are currently run in isolation via the script.

### Release

### Step 1 - update the changelog

- Update `CHANGELOG.md`: this is automated. Use `devenv` and the `commitizen` [tool](https://commitizen-tools.github.io/commitizen/):
  ```
  git fetch --tags origin  # make sure your local tags are same as in github
  cz bump --files-only  # --files-only prevents the tool making a git tag
  ```
  This will use the [commit history](https://www.conventionalcommits.org/) and modify `CHANGELOG.md` to include a heading with the new version number and the date. It also updates `.cz.toml`. The tool automatically decides whether to increment the patch version, minor version or major version (major version changes are currently disabled in its config file). It also updates the version in `pyproject.toml` at the same time.
- If you like, you can manually edit `CHANGELOG.md` at this point. Consider moving important entries under these headings, or writing under them (see [Keep A Changelog](https://keepachangelog.com/en/1.1.0/#how)):
  - Deprecated
  - Removed
  - Security
- Create a release branch `git checkout -b release/vx.y.z`
- `git add` the modifications, then `git commit` and `git push` them.
- Create a PR (title: `docs: Update CHANGELOG for vx.y.z`)
- Ask a colleague to review the changes (should be just `CHANGELOG.md`, `pyproject.toml`, `.cz.toml` and `uv.lock`)
- Squash merge the PR into `main`

### Step 2 - run the release workflow

- Go to https://github.com/CQCL-DEV/qnexus/releases/new
- Select `create new tag... on publish` when choosing the tag, with name in the format `vx.y.z`.
- Choose the target branch/commit for the release (normally `main`)
- Put the version number in the "release title" box
- Copy/paste the new sections from `CHANGELOG.md` into the "Describe this release" box
- Click "Publish release"


## License

This project is licensed under Apache License, Version 2.0 ([LICENSE][] or http://www.apache.org/licenses/LICENSE-2.0).

  [LICENSE]: ./LICENSE

## Dependency Reporting

This project reports its open-source dependencies in a human-readable markdown format in [DEPENDENCIES.md](./DEPENDENCIES.md). This file
is generated via:

```sh
uv run scripts/write_dependencies.sh
```

This file will be checked for differences in the github CI.


Copyright 2025 Quantinuum Ltd.
