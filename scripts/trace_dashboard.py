"""Count the error kinds of the traces in Langfuse and write them as a page.

Usage:  task trace:dashboard [-- --lang tr|en --newest N --output PATH]

Reads the newest observations of the Langfuse project (the keys come from
.env), prints the counts and writes one self-contained HTML file, by default
data/error_tracing.html: no server and no port, so it opens as a file. The
reading and the counting are src/tracing_dashboard.py; this file only runs
them.
"""

import argparse
import sys
from pathlib import Path

import config
from src import tracing_dashboard
from src.i18n import DEFAULT_LANGUAGE, Language, catalog

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "error_tracing.html"


def main(argv: list[str] | None = None) -> int:
    """Run the command line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--lang",
        choices=[language.value for language in Language],
        default=DEFAULT_LANGUAGE.value,
    )
    parser.add_argument(
        "--newest", type=int, default=config.TRACING_DASHBOARD_OBSERVATIONS
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    texts = catalog(Language(args.lang))
    try:
        public, secret = tracing_dashboard.credentials()
        observations = tracing_dashboard.fetch_observations(public, secret, args.newest)
    except tracing_dashboard.DashboardUnavailableError as failure:
        print(tracing_dashboard.failure_text(texts, failure), file=sys.stderr)
        return 1
    rows = tracing_dashboard.count_errors(observations)
    print(tracing_dashboard.render_table(rows, len(observations), texts))
    page = tracing_dashboard.render_html(rows, len(observations), texts, args.lang)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print(texts.DASH_WRITTEN.format(path=args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
