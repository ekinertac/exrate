# exrate

A zero-dependency command-line client for the [Frankfurter](https://frankfurter.dev) v2
foreign-exchange API. Daily reference rates from **84 central banks, 201 currencies,
back to 1948**. No API key, no login, no rate caps for normal use.

It's a single Python file (`exrate.py`, stdlib only) — runs anywhere Python 3.8+ exists.
Every subcommand maps 1:1 to the [Frankfurter OpenAPI spec](https://api.frankfurter.dev/v2/openapi.json),
and every subcommand accepts `--json` for machine-readable output, which also makes
it pleasant to drive from scripts and AI agents.

## Install

From PyPI (recommended):

```bash
pipx install exrate     # isolated, puts `exrate` on your PATH
# or
pip install exrate
```

Or run it once without installing (like `npx`):

```bash
pipx run exrate rate EUR USD
```

From source (symlink install for hacking on it):

```bash
git clone https://github.com/ekinertac/exrate.git
cd exrate
./install.sh        # symlinks exrate.py -> ~/.local/bin/exrate
exrate --help
```

`install.sh` symlinks (not copies) the script, so edits take effect with no reinstall.
It installs into `~/.local/bin`; make sure that's on your `PATH`.

## Usage

```bash
exrate rate EUR USD                              # latest single pair
exrate rate EUR USD --date 2020-03-15            # historical
exrate convert 100 USD JPY                       # convert an amount (client-side)
exrate rates --base USD --quotes EUR,GBP,JPY     # several pairs at once
exrate rates --from 2026-01-01 --quotes USD      # daily time series
exrate rates --from 2026-01-01 --group month     # downsample to monthly
exrate rates --from 2026-01-01 --quotes USD --csv  # native CSV
exrate currencies                                # list currency codes
exrate currencies --all                          # include legacy currencies
exrate currency AED                              # one currency's details + peg
exrate providers                                 # data sources (central banks)
```

Add `--json` to any command for raw API JSON (numbers stay JSON numbers, not strings),
handy for `jq` pipelines:

```bash
exrate currencies --json | jq -r '.[].iso_code'
exrate providers  --json | jq -r '.[].key'
```

Run `exrate <subcommand> --help` for that command's modes, fields, and examples.

## Commands

| Command | Endpoint | Purpose |
|---|---|---|
| `rate BASE QUOTE` | `GET /rate/{base}/{quote}` | One pair, latest or historical |
| `rates` | `GET /rates` | Many rates: latest, a date, or a time series |
| `convert AMOUNT FROM TO` | *(client-side)* | Multiply amount by the pair rate |
| `currencies` | `GET /currencies` | List supported currency codes |
| `currency CODE` | `GET /currency/{code}` | One currency's details + peg metadata |
| `providers` | `GET /providers` | Data providers (central banks) and their keys |

## Conventions

- **Currency codes** are ISO 4217, 3 letters, case-insensitive (`eur` == `EUR`).
- **Dates** are `YYYY-MM-DD`. Weekends/holidays return the last published rate.
- **Default base** is `EUR`. The base is the "1 unit" side; the rate says how many
  quote units equal 1 base unit.
- **Providers**: rates are *blended* across providers by default. Pass `--providers ECB`
  to pin a single official source.
- **Conversion** is client-side — the API has no conversion endpoint, so `convert`
  fetches the pair rate and multiplies (matching the official docs' approach).

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | API or network error (message on stderr, e.g. unknown currency) |
| `2` | Bad usage / invalid arguments |

## Releasing

Versions are single-sourced from `__version__` in `exrate.py`. To cut a release:

1. Bump `__version__` in `exrate.py`.
2. Commit and tag: `git tag v1.2.3 && git push --tags`.
3. On GitHub: **Releases → Draft a new release**, pick the tag, **Publish**.

Publishing a GitHub Release triggers `.github/workflows/publish.yml`, which builds
the sdist + wheel and uploads them to PyPI via **Trusted Publishing** (OIDC, no
stored tokens). One-time PyPI setup before the first Actions run:

> PyPI → *Your projects* / *Publishing* → **Add a pending publisher**
> · Owner: `ekinertac` · Repository: `exrate`
> · Workflow: `publish.yml` · Environment: `pypi`

To build/publish manually instead:

```bash
pipx run build                 # -> dist/*.tar.gz, dist/*.whl
pipx run twine check dist/*
pipx run twine upload dist/*   # prompts for a PyPI API token
```

## License

MIT
