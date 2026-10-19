# FlakeHunter

[![CI](https://github.com/rayssi/flakehunter/actions/workflows/ci.yml/badge.svg)](https://github.com/rayssi/flakehunter/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/flakehunter)](https://pypi.org/project/flakehunter/)
[![Python](https://img.shields.io/pypi/pyversions/flakehunter)](https://pypi.org/project/flakehunter/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/rayssi/flakehunter/blob/main/LICENSE)

FlakeHunter reads the history of your Allure results and tells you, on every GitLab pipeline:

- which tests are **broken** (a real bug, failing on every run for a while);
- which tests are **flaky** (they pass and fail for no reason);
- which tests are getting **slower**;
- how long the suite takes, run after run.

No more downloading the history and running scripts locally: everything happens in the GitLab job.

![FlakeHunter report](https://raw.githubusercontent.com/rayssi/flakehunter/main/docs/report.png)

## Why another tool?

Most tools measure the **failure rate**. Yet these two tests have the same failure rate (40%):

```
test_payment   ✓ ✓ ✓ ✓ ✓ ✓ ✗ ✗ ✗ ✗    broken since the 7th run: a real bug
test_login     ✓ ✗ ✓ ✗ ✓ ✓ ✗ ✓ ✗ ✓    flaky: it keeps flipping
```

FlakeHunter looks at the **order** of the results, retries included. It tells real bugs apart from flaky tests.

## What you get

On every pipeline, in the `flakehunter-report/` folder:

| Output | Content |
|---|---|
| job log | a short summary, readable right in GitLab |
| `index.html` | the full report, works offline, light and dark mode |
| `summary.json` | every metric, for other tools (Slack, dashboards…), with a `schema_version` field |

## Install

```bash
pip install flakehunter
```

Python 3.10 or later. No dependencies.

## Use it in GitLab CI

FlakeHunter reads a `results-history/` folder: one `YYYY-MM-DD_<pipeline>.tar.gz` archive per run, containing the Allure `*-result.json` files, kept from one pipeline to the next by the GitLab cache.

To build that folder, add this step to the job that generates your Allure report:

```yaml
- mkdir -p results-history
- RUN_NAME="$(date +%Y-%m-%d)_${CI_PIPELINE_ID}"
- mkdir -p "raw-tmp/${RUN_NAME}"
- cp allure-results/*-result.json "raw-tmp/${RUN_NAME}/" 2>/dev/null || true
- tar -czf "results-history/${RUN_NAME}.tar.gz" -C raw-tmp "${RUN_NAME}"
- rm -rf raw-tmp
- find results-history -maxdepth 1 -name '*.tar.gz' -mtime +30 -delete
```

Then add the FlakeHunter job:

```yaml
flakehunter_uat:
  stage: report
  image: python:3.12-slim
  needs:
    - job: generate_allure_report_uat
      artifacts: true
  script:
    - pip install --quiet flakehunter
    - flakehunter analyze --history results-history --env UAT
  artifacts:
    when: always
    expose_as: "FlakeHunter"
    paths: [flakehunter-report/]
    expire_in: 30 days
```

A full example with several environments is in [`examples/gitlab-ci.yml`](https://github.com/rayssi/flakehunter/blob/main/examples/gitlab-ci.yml).

## Use it locally

```bash
flakehunter analyze --history path/to/results-history --env UAT
```

The folder can also contain one sub-folder per run, or be a single `allure-results/` folder.

## How tests are classified

Every attempt of a test is put in a row, retries included. FlakeHunter counts the **flips**: passed to failed, or the other way round.

| Category | Default rule |
|---|---|
| Broken | failing on the last 3 runs or more, after passing before |
| Always failing | failing on every run since it was added |
| Flaky | at least 3 flips, or at least 2 passes obtained only on retry |
| Watch | a few failures, not enough to draw a conclusion |
| Stable | no failure |
| Inactive | missing from the last 3 runs (renamed, deleted…), left out of the lists |

The **flakiness** score is the number of flips divided by the number of attempts minus one: 0 for a test that never changes, close to 1 for a test that changes on every attempt.

**Durations** are computed on passing executions only (Min, Q1, Median, Avg, Q3, Max and relative spread). A **slowdown** compares the median of the last 7 days with the median before; it is reported from +20% and +1s.

## Options

| Option | Default | Purpose |
|---|---|---|
| `--history DIR` | `results-history` | history folder |
| `--env NAME` | `$TEST_ENV` | environment name shown in the report |
| `--out DIR` | `flakehunter-report` | report folder |
| `--min-flips N` | 3 | flips needed to be flaky |
| `--broken-streak N` | 3 | consecutive failures needed to be broken |
| `--recent-days N` | 7 | recent window for slowdowns |
| `--slowdown PCT` | 20 | median increase reported as a slowdown, in % |
| `--min-passes N` | 2 | minimum passing runs for duration statistics |
| `--band P` | 25 | spread = (P[100-P] − P[P]) / median |
| `--active-runs N` | 3 | a test missing from the last N runs is ignored |
| `--top N` | 10 | tests shown per section in the log |
| `--fail-on` | `never` | `broken` or `flaky` to fail the job |

## Try it with demo data

```bash
python examples/make_demo_history.py --out demo/results-history
flakehunter analyze --history demo/results-history --env DEMO
```

## Privacy and security

- **No dependencies.** FlakeHunter only uses the Python standard library.
- **No network access.** It never sends your data anywhere and works offline.
- **Read-only.** It reads your results history and only writes to its own output folder.
  Archives are read in memory and never extracted to disk.
- **Safe report.** Test names and error messages are escaped in the HTML report.

## Development

See [CONTRIBUTING.md](https://github.com/rayssi/flakehunter/blob/main/CONTRIBUTING.md) to set up the project and run the checks.
Changes are listed in [CHANGELOG.md](https://github.com/rayssi/flakehunter/blob/main/CHANGELOG.md).

## Roadmap

- automatic comment in the merge request;
- weekly summary on Slack or Teams;
- a GitLab CI/CD component, to add it in 4 lines;
- direct support for Playwright's JSON report, for projects without Allure.

## License

MIT. Copyright (c) 2026 Houssem RAISSI.
