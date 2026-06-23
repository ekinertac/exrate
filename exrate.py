#!/usr/bin/env python3
"""
exrate — a zero-dependency command-line client for the Frankfurter v2 API.

What this file is:
    The entire CLI tool. It is a single self-contained Python script (stdlib only)
    that wraps every endpoint of the Frankfurter foreign-exchange API
    (https://api.frankfurter.dev/v2, OpenAPI 2.1.1) behind ergonomic subcommands.

Where it fits:
    This is the only source file in the project. It is installed as the `exrate`
    executable onto the user's PATH (see install.sh). There is no package, no
    network library, and no config — it talks HTTP via urllib so it runs anywhere
    Python 3.8+ exists.

API surface mapped to subcommands:
    GET /rate/{base}/{quote}  -> `exrate rate BASE QUOTE`        (single pair)
    GET /rates                -> `exrate rates`                  (latest / historical / time-series)
    (client-side conversion)  -> `exrate convert AMOUNT FROM TO` (no server endpoint; we multiply)
    GET /currencies           -> `exrate currencies`
    GET /currency/{code}      -> `exrate currency CODE`
    GET /providers            -> `exrate providers`

Design notes / constraints:
    - The API has no conversion endpoint by design, so `convert` fetches the pair
      rate and multiplies locally (matching the JS snippet in the official docs).
    - Every command accepts `--json` to emit the raw API JSON for scripting; the
      default is a human-readable table. `rates --csv` proxies the API's native
      CSV output (.csv suffix on the path).
    - Errors from the API (400/404/422) carry a JSON `{"message": ...}` body which
      we surface verbatim with a non-zero exit code.
    - Base currency defaults to EUR server-side; we don't second-guess that.

Related reading: the OpenAPI spec at https://api.frankfurter.dev/v2/openapi.json
is the source of truth for parameters and is what this CLI was generated against.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

# Single source of truth for the version: pyproject.toml reads this attribute
# (hatchling dynamic version), and --version prints it. Bump here only.
__version__ = "1.0.1"

API_BASE = "https://api.frankfurter.dev/v2"
USER_AGENT = f"exrate-cli/{__version__} (+https://api.frankfurter.dev)"


# --- HTTP layer -------------------------------------------------------------

def _request(path, params=None, accept="application/json"):
    """Perform a GET against the Frankfurter API.

    Returns the parsed body (dict/list for JSON, str for csv/ndjson). Raises
    SystemExit with the API's error message on any 4xx/5xx so the CLI exits
    cleanly instead of dumping a traceback.
    """
    query = ""
    if params:
        # Drop unset (None) params so we never send empty query values.
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            query = "?" + urllib.parse.urlencode(clean)
    url = f"{API_BASE}{path}{query}"
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        msg = detail
        try:
            msg = json.loads(detail).get("message", detail)
        except (ValueError, AttributeError):
            pass
        _die(f"API error {e.code}: {msg}")
    except urllib.error.URLError as e:
        _die(f"Network error: {e.reason}")

    if accept == "application/json":
        return json.loads(body)
    return body  # csv / ndjson passthrough


def _die(message, code=1):
    print(message, file=sys.stderr)
    raise SystemExit(code)


# --- Output helpers ---------------------------------------------------------

def _print_json(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _table(rows, headers):
    """Render a list of row-lists as a simple aligned ASCII table."""
    if not rows:
        print("(no results)")
        return
    cols = list(zip(*([headers] + rows)))
    widths = [max(len(str(cell)) for cell in col) for col in cols]
    line = "  ".join(str(h).ljust(w) for h, w in zip(headers, widths))
    print(line)
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(str(c).ljust(w) for c, w in zip(row, widths)))


# --- Subcommand handlers ----------------------------------------------------

def cmd_rate(args):
    """Single currency pair: GET /rate/{base}/{quote}."""
    base = args.base.upper()
    quote = args.quote.upper()
    data = _request(
        f"/rate/{urllib.parse.quote(base)}/{urllib.parse.quote(quote)}",
        {"date": args.date, "providers": args.providers},
    )
    if args.json:
        _print_json(data)
        return
    print(f"{data['date']}  1 {data['base']} = {data['rate']} {data['quote']}")


def cmd_rates(args):
    """Latest / historical / time-series rates: GET /rates."""
    params = {
        "base": args.base,
        "quotes": args.quotes,
        "date": args.date,
        "from": getattr(args, "from"),
        "to": args.to,
        "group": args.group,
        "expand": "providers" if args.expand else None,
        "providers": args.providers,
    }
    if args.csv:
        # The API exposes native CSV via a .csv suffix on the path.
        print(_request("/rates.csv", params, accept="text/csv").rstrip("\n"))
        return
    data = _request("/rates", params)
    if args.json:
        _print_json(data)
        return
    rows = [[r["date"], r["base"], r["quote"], r["rate"]] for r in data]
    _table(rows, ["DATE", "BASE", "QUOTE", "RATE"])


def cmd_convert(args):
    """Client-side conversion (the API has no conversion endpoint)."""
    base = args.base.upper()
    quote = args.quote.upper()
    data = _request(
        f"/rate/{urllib.parse.quote(base)}/{urllib.parse.quote(quote)}",
        {"date": args.date},
    )
    result = args.amount * data["rate"]
    if args.json:
        _print_json({
            "date": data["date"],
            "base": base,
            "quote": quote,
            "amount": args.amount,
            "rate": data["rate"],
            "result": result,
        })
        return
    print(f"{args.amount:g} {base} = {result:,.4f} {quote}  "
          f"(rate {data['rate']} on {data['date']})")


def cmd_currencies(args):
    """List currencies: GET /currencies."""
    data = _request(
        "/currencies",
        {"scope": "all" if args.all else None, "providers": args.providers},
    )
    if args.json:
        _print_json(data)
        return
    rows = [[c.get("iso_code", ""), c.get("symbol") or "", c.get("name", "")] for c in data]
    rows.sort(key=lambda r: r[0])
    _table(rows, ["CODE", "SYM", "NAME"])
    print(f"\n{len(rows)} currencies")


def cmd_currency(args):
    """Single currency detail: GET /currency/{code}."""
    code = args.code.upper()
    data = _request(f"/currency/{urllib.parse.quote(code)}")
    if args.json:
        _print_json(data)
        return
    print(f"{data['iso_code']}  {data.get('symbol') or ''}  {data['name']}")
    if data.get("iso_numeric"):
        print(f"  ISO numeric : {data['iso_numeric']}")
    if data.get("providers"):
        print(f"  Providers   : {', '.join(data['providers'])}")
    if data.get("peg"):
        peg = data["peg"]
        print(f"  Peg         : 1 {data['iso_code']} = {peg.get('rate')} {peg.get('base')} "
              f"({peg.get('authority', '')})")


def cmd_providers(args):
    """List data providers: GET /providers."""
    data = _request("/providers")
    if args.json:
        _print_json(data)
        return
    rows = [[
        p.get("key", ""),
        p.get("country_code") or "",
        p.get("pivot_currency") or "",
        p.get("name", ""),
    ] for p in data]
    rows.sort(key=lambda r: r[0])
    _table(rows, ["KEY", "CC", "PIVOT", "NAME"])
    print(f"\n{len(rows)} providers")


# --- Argument parser --------------------------------------------------------

# Shared prose reused across the top-level and sub-command help. Written for
# agents as much as humans: it states the input conventions, defaults, output
# contract, and exit codes explicitly so a tool-using model never has to guess.
CONVENTIONS = """\
CONVENTIONS
  Currency codes : ISO 4217, 3 letters, case-insensitive (eur == EUR).
                   List valid codes with `exrate currencies`.
  Dates          : YYYY-MM-DD. Data goes back to 1948; future dates clamp to
                   the latest available. Weekends/holidays return the last
                   published rate.
  Default base   : EUR when --base is omitted. The base is the "1 unit" side;
                   the rate tells you how many quote units equal 1 base unit.
  Providers      : "central banks" (run `exrate providers` for keys like ECB,
                   FRED). Default rates are BLENDED across providers; pass
                   --providers to pin a single official source.
  Auth           : none. No API key, no login, no rate caps for normal use.

OUTPUT (for scripting / parsing)
  Default        : a human-readable aligned table on stdout.
  --json         : raw API JSON on stdout — use this when parsing with jq or
                   feeding another program. Stable field names: date, base,
                   quote, rate (numbers are JSON numbers, not strings).
  --csv          : `rates` only; the API's native CSV with a header row.

EXIT CODES
  0  success
  1  API or network error (message printed to stderr, e.g. unknown currency)
  2  bad usage / invalid arguments (argparse message to stderr)
"""

EPILOG_MAIN = CONVENTIONS + """
EXAMPLES
  exrate rate EUR USD                       # latest 1 EUR -> USD
  exrate rate EUR USD --date 2020-03-15     # historical
  exrate convert 100 USD JPY                # convert an amount
  exrate rates --base USD --quotes EUR,GBP  # several pairs at once
  exrate rates --from 2026-01-01 --quotes USD            # daily time series
  exrate rates --from 2026-01-01 --group month --json    # monthly, as JSON
  exrate currencies --json | jq -r '.[].iso_code'        # script the code list
  exrate currency AED                       # details + peg, if any
  exrate providers                          # data sources / their keys
"""


def build_parser():
    p = argparse.ArgumentParser(
        prog="exrate",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="exrate — foreign-exchange rates from the Frankfurter API "
                    "(api.frankfurter.dev).\n"
                    "Daily reference rates from 84 central banks, 201 currencies, "
                    "back to 1948. No API key needed.\n\n"
                    "Pick a subcommand below. Every subcommand accepts --json for "
                    "machine-readable output.\n"
                    "Run `exrate <subcommand> --help` for that command's options "
                    "and examples.",
        epilog=EPILOG_MAIN,
    )
    p.add_argument("-V", "--version", action="version", version=f"exrate {__version__}")
    # Not required: running `exrate` with no args prints full help (see main()),
    # which is friendlier for an agent probing the tool than an error.
    sub = p.add_subparsers(dest="command", metavar="<subcommand>")

    def subparser(name, summary, description):
        return sub.add_parser(
            name,
            help=summary,
            description=description,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )

    # rate
    s = subparser(
        "rate",
        "Latest or historical rate for ONE currency pair",
        "Get the exchange rate for a single BASE -> QUOTE pair.\n"
        "Returns one number: how many QUOTE units equal 1 BASE unit.\n\n"
        "Default output:  '2026-06-23  1 EUR = 1.1439 USD'\n"
        "--json fields:   date, base, quote, rate\n\n"
        "Examples:\n"
        "  exrate rate EUR USD\n"
        "  exrate rate GBP JPY --date 2015-01-02\n"
        "  exrate rate EUR USD --providers ECB --json",
    )
    s.add_argument("base", help="Base currency code (the '1 unit' side), e.g. EUR")
    s.add_argument("quote", help="Quote currency code (the priced side), e.g. USD")
    s.add_argument("--date", metavar="YYYY-MM-DD", help="Historical date (default: latest available)")
    s.add_argument("--providers", metavar="KEYS", help="Pin to specific provider key(s), comma-separated, e.g. ECB")
    s.add_argument("--json", action="store_true", help="Emit raw JSON instead of a line of text")
    s.set_defaults(func=cmd_rate)

    # rates
    s = subparser(
        "rates",
        "Many rates at once: latest, a single date, or a time series",
        "Get multiple rates from one base currency. Three modes:\n"
        "  latest      : (no date flags)         all/most pairs for today\n"
        "  single date : --date YYYY-MM-DD       all/most pairs on that day\n"
        "  time series : --from [--to]           one row per day in the range\n\n"
        "Narrow the result with --quotes (fewer columns = smaller, faster).\n"
        "Default output is a table; use --json to parse or --csv for spreadsheets.\n\n"
        "--json fields per row: date, base, quote, rate (+ providers[] with --expand)\n\n"
        "Examples:\n"
        "  exrate rates                                   # everything vs EUR, today\n"
        "  exrate rates --base USD --quotes EUR,GBP,JPY\n"
        "  exrate rates --date 1999-01-04\n"
        "  exrate rates --from 2026-01-01 --to 2026-03-31 --quotes USD\n"
        "  exrate rates --from 2026-01-01 --group month --quotes USD --csv\n"
        "  exrate rates --quotes USD --expand --json      # per-provider breakdown",
    )
    s.add_argument("--base", metavar="CODE", help="Base currency (default: EUR)")
    s.add_argument("--quotes", metavar="CODES", help="Comma-separated quote currencies to include (default: all)")
    s.add_argument("--date", metavar="YYYY-MM-DD", help="Single historical date (mutually exclusive with --from/--to)")
    s.add_argument("--from", dest="from", metavar="YYYY-MM-DD", help="Start of a date range (turns on time-series mode)")
    s.add_argument("--to", metavar="YYYY-MM-DD", help="End of the date range (default: today)")
    s.add_argument("--group", choices=["week", "month"], help="Downsample a time series to one row per week/month")
    s.add_argument("--providers", metavar="KEYS", help="Pin to specific provider key(s), comma-separated")
    s.add_argument("--expand", action="store_true", help="Add per-provider attribution to each row (JSON output only)")
    s.add_argument("--csv", action="store_true", help="Output the API's native CSV (header + rows)")
    s.add_argument("--json", action="store_true", help="Emit raw JSON")
    s.set_defaults(func=cmd_rates)

    # convert
    s = subparser(
        "convert",
        "Convert an AMOUNT from one currency to another",
        "Convert AMOUNT of BASE into QUOTE at the latest (or historical) rate.\n"
        "Done client-side: the Frankfurter API has no conversion endpoint, so\n"
        "this fetches the pair rate and multiplies.\n\n"
        "Default output: '100 USD = 16,172.0000 JPY  (rate 161.72 on 2026-06-23)'\n"
        "--json fields:  date, base, quote, amount, rate, result\n\n"
        "Examples:\n"
        "  exrate convert 100 USD JPY\n"
        "  exrate convert 49.99 EUR GBP --date 2020-01-02 --json",
    )
    s.add_argument("amount", type=float, help="Numeric amount to convert, e.g. 100 or 49.99")
    s.add_argument("base", help="Currency to convert FROM, e.g. USD")
    s.add_argument("quote", help="Currency to convert TO, e.g. JPY")
    s.add_argument("--date", metavar="YYYY-MM-DD", help="Use the rate from this date (default: latest)")
    s.add_argument("--json", action="store_true", help="Emit raw JSON")
    s.set_defaults(func=cmd_convert)

    # currencies
    s = subparser(
        "currencies",
        "List supported currency codes and names",
        "List every supported currency (ISO code, symbol, full name).\n"
        "Use this to discover valid codes for the other subcommands.\n\n"
        "--json fields per item: iso_code, iso_numeric, name, symbol, start_date, end_date\n\n"
        "Examples:\n"
        "  exrate currencies\n"
        "  exrate currencies --all                        # include legacy currencies\n"
        "  exrate currencies --json | jq -r '.[].iso_code'",
    )
    s.add_argument("--all", action="store_true", help="Include legacy/retired currencies (scope=all)")
    s.add_argument("--providers", metavar="KEYS", help="Limit to currencies covered by given provider key(s)")
    s.add_argument("--json", action="store_true", help="Emit raw JSON")
    s.set_defaults(func=cmd_currencies)

    # currency
    s = subparser(
        "currency",
        "Details for ONE currency (providers, peg)",
        "Show details for a single currency: name, symbol, the providers that\n"
        "publish it, and peg metadata when the currency is pegged.\n\n"
        "--json fields: iso_code, iso_numeric, name, symbol, providers[], peg{...}\n\n"
        "Examples:\n"
        "  exrate currency EUR\n"
        "  exrate currency AED       # shows the USD peg\n"
        "  exrate currency JPY --json",
    )
    s.add_argument("code", help="Currency code, e.g. EUR")
    s.add_argument("--json", action="store_true", help="Emit raw JSON")
    s.set_defaults(func=cmd_currency)

    # providers
    s = subparser(
        "providers",
        "List data providers (central banks) and their keys",
        "List the data sources behind the rates. The KEY column is what you pass\n"
        "to --providers on other commands (e.g. ECB, FRED).\n\n"
        "--json fields: key, name, country_code, rate_type, pivot_currency, "
        "currencies[], ...\n\n"
        "Examples:\n"
        "  exrate providers\n"
        "  exrate providers --json | jq -r '.[].key'",
    )
    s.add_argument("--json", action="store_true", help="Emit raw JSON")
    s.set_defaults(func=cmd_providers)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    # No subcommand given -> print full help to stdout and exit 0. Friendlier for
    # an agent (or human) discovering the tool than argparse's terse usage error.
    if getattr(args, "func", None) is None:
        parser.print_help()
        return
    try:
        args.func(args)
    except BrokenPipeError:
        # Allow piping into head/less without a noisy traceback.
        sys.stderr.close()


if __name__ == "__main__":
    main()
