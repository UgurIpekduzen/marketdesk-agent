"""Put a new secret key for the id hashes into .env, unless one is there.

Usage:  python scripts/set_hash_key.py [--env .env]

The key is written to the file and never printed. An existing key is left
alone: changing it would make new hashes differ from the ones already in
logs and traces.
"""

import argparse
import secrets
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Run as a plain script, Python only searches the scripts/ folder for imports.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.guardrails.pii import HASH_KEY_VARIABLE

DEFAULT_ENV_PATH = Path(".env")


def set_hash_key(env_path: Path) -> bool:
    """Write a new key into the file; False if it already holds one."""
    lines = env_path.read_text(encoding="utf-8").splitlines()
    prefix = f"{HASH_KEY_VARIABLE}="
    new_line = prefix + secrets.token_hex(32)
    for number, line in enumerate(lines):
        if line.startswith(prefix):
            if line[len(prefix) :].strip():
                return False
            # The name is there without a value: fill it in.
            lines[number] = new_line
            break
    else:
        lines.append(new_line)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV_PATH)
    args = parser.parse_args()

    if not args.env.exists():
        print(f"{args.env} does not exist. Create it first: cp .env.example .env")
        return 1
    if set_hash_key(args.env):
        print(f"{HASH_KEY_VARIABLE} was written to {args.env}.")
    else:
        print(f"{args.env} already has a {HASH_KEY_VARIABLE}; it was left as it is.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
