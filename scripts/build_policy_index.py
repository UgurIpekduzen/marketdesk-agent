"""Build both policy indexes from the documents in policies/: the direct
Chroma one and the one built through LlamaIndex.

Usage:  python scripts/build_policy_index.py

Run it after any change to a policy document or to the embedding model
settings. It downloads the embedding model on first use.
"""

import sys
from pathlib import Path

# Run as a plain script, Python only searches the scripts/ folder for imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.knowledge import llamaindex_policy_index, policy_index
from src.knowledge.embedding import load_embedder
from src.knowledge.policy_index import PROJECT_ROOT


def main() -> int:
    embedder = load_embedder()
    for module in (policy_index, llamaindex_policy_index):
        count = module.build_index(embedder)
        print(f"{count} sections written to {module.INDEX_DIR.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
