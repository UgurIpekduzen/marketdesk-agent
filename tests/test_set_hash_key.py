"""Tests for the script that writes the id hash key into .env."""

from scripts.set_hash_key import main, set_hash_key
from src.guardrails.pii import HASH_KEY_VARIABLE

PREFIX = f"{HASH_KEY_VARIABLE}="


def key_in(env_path) -> str:
    (line,) = [
        line for line in env_path.read_text().splitlines() if line.startswith(PREFIX)
    ]
    return line[len(PREFIX) :]


def test_key_is_added_and_the_other_lines_are_kept(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("# keys\nGEMINI_API_KEY_FREE=abc\n")

    assert set_hash_key(env_path)

    assert env_path.read_text().startswith("# keys\nGEMINI_API_KEY_FREE=abc\n")
    assert len(key_in(env_path)) == 64


def test_empty_entry_is_filled_in_where_it_stands(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(f"{PREFIX}\nGROQ_API_KEY=xyz\n")

    assert set_hash_key(env_path)

    assert env_path.read_text().splitlines()[1] == "GROQ_API_KEY=xyz"
    assert len(key_in(env_path)) == 64


def test_existing_key_is_left_alone(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(f"{PREFIX}already-set\n")

    assert not set_hash_key(env_path)

    assert key_in(env_path) == "already-set"


def test_two_files_get_different_keys(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.write_text("")
    second.write_text("")

    set_hash_key(first)
    set_hash_key(second)

    assert key_in(first) != key_in(second)


def test_key_is_never_printed(tmp_path, monkeypatch, capsys):
    env_path = tmp_path / ".env"
    env_path.write_text("")
    monkeypatch.setattr("sys.argv", ["set_hash_key.py", "--env", str(env_path)])

    assert main() == 0

    printed = capsys.readouterr().out
    assert HASH_KEY_VARIABLE in printed
    assert key_in(env_path) not in printed


def test_missing_file_is_reported(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["set_hash_key.py", "--env", str(tmp_path / "no")])

    assert main() == 1
    assert "does not exist" in capsys.readouterr().out
