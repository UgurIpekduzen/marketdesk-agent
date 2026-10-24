"""The order server with one guard broken, for eval/mutations.py only.

Usage:  python -m eval.mutated_server NAME

Started in place of src.mcp_server.server by the mutation test setup. The
application never starts it.
"""

import sys
from contextlib import ExitStack

from eval.mutations import apply


def main(name: str) -> None:
    with ExitStack() as stack:
        apply(name, stack)
        from src.mcp_server import server

        server.server.run(transport="stdio")


if __name__ == "__main__":
    main(sys.argv[1])
