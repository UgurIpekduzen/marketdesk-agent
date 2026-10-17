"""Build the policy index from the documents in policies/.

Usage:  python scripts/build_policy_index.py

Run it after any change to a policy document or to the embedding model
settings. It downloads the embedding model on first use.
"""

import sys
from pathlib import Path

# Run as a plain script, Python only searches the scripts/ folder for imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.knowledge.embedding import load_embedder
from src.knowledge.policy_index import INDEX_DIR, PROJECT_ROOT, build_index


def main() -> int:
    count = build_index(load_embedder())
    print(f"{count} sections written to {INDEX_DIR.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
