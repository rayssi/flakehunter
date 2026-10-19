# Changelog

All notable changes to FlakeHunter are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-19

### Added

- `flakehunter analyze` command, reading a `results-history/` folder of Allure results
  (one `.tar.gz` archive per run, one sub-folder per run, or a single `allure-results/` folder).
- Classification of every test: broken, always failing, flaky, watch, stable, inactive.
- Flakiness score based on flips between attempts, retries included, so real regressions
  are not mistaken for flaky tests.
- Duration statistics on passing runs (min, Q1, median, average, Q3, max, spread) and
  slowdown detection over a recent window.
- Short summary in the job log, self-contained HTML report (light and dark mode) and
  `summary.json` (schema version 1).
- `--fail-on` option to fail the job on broken or flaky tests.

[Unreleased]: https://github.com/rayssi/flakehunter/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/rayssi/flakehunter/releases/tag/v0.1.0
