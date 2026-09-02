# Project J.A.R.V.I.S. CI v0.2.1

Status: approved

## Goal

Add the first small continuous integration foundation for Project J.A.R.V.I.S.

This milestone answers one question:

Can every pull request and main-branch push run the existing Python verification suite on Linux and Windows without requiring Ollama, secrets, or external services after dependency installation?

## Implement

- GitHub Actions workflow at `.github/workflows/ci.yml`
- Automatic CI runs for pull requests targeting `main`
- Automatic CI runs for pushes to `main`
- Python 3.12 setup
- Matrix testing on:
  - `ubuntu-latest`
  - `windows-latest`
- Editable project installation with:

```bash
python -m pip install -e .[dev]
```

- Test execution with:

```bash
python -m pytest
```

- Compile check with:

```bash
python -m compileall src tests
```

- Read-only repository permissions where practical
- Concurrency settings that cancel superseded runs for the same branch or pull request

## Do Not Implement

- Deployment
- Releases
- Docker
- Packaging changes
- Code coverage services
- External SaaS integrations
- New JARVIS functionality
- Ollama service startup
- Secrets or API keys
- Application version bump

## CI Workflow

The workflow should remain boring and easy to inspect.

Required behavior:

- Trigger on `pull_request` events targeting `main`.
- Trigger on `push` events to `main`.
- Use Python 3.12.
- Run on both Ubuntu and Windows.
- Install the project with the documented editable install command.
- Run the existing pytest suite.
- Run Python compile checks.
- Require no Ollama server.
- Require no network services after dependency installation.
- Require no secrets or API keys.
- Use read-only repository permissions where practical.
- Cancel superseded CI runs for the same pull request or branch.

## Acceptance Criteria

- `.github/workflows/ci.yml` exists.
- The workflow is valid GitHub Actions YAML.
- The workflow targets `pull_request` to `main` and `push` to `main`.
- The workflow runs on `ubuntu-latest` and `windows-latest`.
- The workflow uses Python 3.12.
- The workflow installs with `python -m pip install -e .[dev]`.
- The workflow runs `python -m pytest`.
- The workflow runs `python -m compileall src tests`.
- The workflow does not require Ollama, credentials, secrets, or external services after dependency installation.
- The workflow uses read-only repository permissions where practical.
- The workflow cancels superseded runs for the same branch or pull request.
- Local tests still pass.
- No JARVIS application version is changed.
- No new product functionality is added.

## Definition Of Done

Another developer should be able to see the required project verification directly in GitHub Actions for a pull request without reverse-engineering local setup.

## Constraints

- Keep the change infrastructure-only.
- Keep the workflow minimal.
- Do not introduce new runtime dependencies.
- Do not add code coverage, deployment, packaging, Docker, release automation, or external services.
- Do not weaken or remove existing tests.
- Do not silently change this task's acceptance criteria.

## Expected Completion Report

When implementation is complete, report:

- Branch
- Commit SHA
- Pull request link
- Files changed
- Local test results
- Compile check result
- Diff check result
- Confirmation that GitHub Actions started
- Status of the Ubuntu CI job
- Status of the Windows CI job
