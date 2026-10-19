# Contributing to FlakeHunter

Thanks for helping! Bug reports, ideas and pull requests are all welcome.

## Set up

```bash
git clone https://github.com/your-name/flakehunter.git
cd flakehunter
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Before opening a pull request

Run the same checks as the CI:

```bash
ruff format .                    # format the code
ruff check .                     # lint
mypy                             # type check (strict)
bandit -c pyproject.toml -r src  # security check
pytest --cov                     # tests and coverage
```

Try your change on demo data:

```bash
python examples/make_demo_history.py --out demo/results-history
flakehunter analyze --history demo/results-history --env DEMO
```

## Guidelines

- Keep FlakeHunter free of runtime dependencies: only the Python standard library.
- Never send data over the network, and never write outside the output folder.
- Add a test for every bug fix and every new behavior.
- Add a line to `CHANGELOG.md`, under "Unreleased".
- If you change `summary.json` in a breaking way, bump `SCHEMA_VERSION`.
