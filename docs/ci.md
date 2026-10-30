# Pull request checks

`.github/workflows/ci.yml` runs on every pull request and pushes to `main`.
It needs no provider secrets. The `backend` job installs CPU-only PyTorch and
FFmpeg, runs application unittest tests, both unittest and pytest agent tests,
and the three existing Node editor/canvas suites. The `frontend` job uses
Node 20 and runs a clean npm install, lint, tests, and the production build.

Install test dependencies locally with `python -m pip install -r requirements-dev.txt`.
Run application tests with `CASCADE_WARM_MODELS=0`, `CASCADE_STORAGE=local`,
and `CASCADE_METADATA_STORE=local`; run agent tests with `python -m pytest backend/tests -q`.
Run Node suites from the repository root and npm commands from `frontend/`.

Chrome suites are preserved and skipped unless `CASCADE_BROWSER_TESTS=1`.
Opting in also requires isolated Chrome with DevTools on port 9333 and the
corresponding fixture server. Paid smoke checks under `tests/manual/` are
excluded from CI.

Repository administrators must require the `backend` and `frontend` checks
in the protection rule/ruleset for `main`. Workflow files alone cannot enable
merge protection. Verify both jobs on a pull request, then verify a deliberately
failing test on a temporary branch makes the corresponding check fail.
