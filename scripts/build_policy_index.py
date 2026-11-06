"""Build the policy index from the documents in policies/.

Usage:  python -m scripts.build_policy_index

Run it after any change to a policy document or to the embedding model
settings. It downloads the embedding model on first use.
"""

import sys

from src.knowledge.embedding import load_embedder
from src.knowledge.policy_index import INDEX_DIR, PROJECT_ROOT, build_index


def main() -> int:
    """Run the command line entry point."""
    count = build_index(load_embedder())
    print(f"{count} sections written to {INDEX_DIR.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
