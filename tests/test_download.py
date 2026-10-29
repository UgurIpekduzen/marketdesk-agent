"""Tests for data/download.py. No network: kagglehub is replaced by a fake."""

import pytest

from data import download as download_module


@pytest.fixture
def fake_dataset(tmp_path, monkeypatch):
    """A folder that stands in for the kagglehub download, with tiny files."""
    source = tmp_path / "kaggle"
    source.mkdir()
    for name in download_module.EXPECTED_FILES:
        (source / name).write_text("header\nrow\n")
    monkeypatch.setattr(
        download_module.kagglehub,
        "dataset_download",
        lambda handle, output_dir=None: str(source),
    )
    return source


def test_download_copies_every_expected_file(fake_dataset, tmp_path):
    raw_dir = tmp_path / "raw"

    result = download_module.download(raw_dir)

    assert result == raw_dir
    assert sorted(p.name for p in raw_dir.iterdir()) == sorted(
        download_module.EXPECTED_FILES
    )
    assert (raw_dir / "olist_orders_dataset.csv").read_text() == "header\nrow\n"


def test_download_can_run_twice(fake_dataset, tmp_path):
    raw_dir = tmp_path / "raw"

    download_module.download(raw_dir)
    download_module.download(raw_dir)

    assert len(list(raw_dir.iterdir())) == len(download_module.EXPECTED_FILES)


def test_download_fails_on_missing_file(fake_dataset, tmp_path):
    (fake_dataset / "olist_orders_dataset.csv").unlink()
    raw_dir = tmp_path / "raw"

    with pytest.raises(FileNotFoundError, match="olist_orders_dataset.csv"):
        download_module.download(raw_dir)

    assert not raw_dir.exists()


def test_dataset_is_pinned_to_a_version():
    assert "/versions/" in download_module.DATASET


def test_fetch_downloads_to_given_folder(fake_dataset, tmp_path, monkeypatch):
    folder = tmp_path / "demo"
    asked = []

    def fake_download(handle, output_dir=None):
        asked.append(output_dir)
        return str(fake_dataset)

    monkeypatch.setattr(download_module.kagglehub, "dataset_download", fake_download)

    assert download_module.fetch(folder) == fake_dataset
    assert asked == [str(folder)]


def test_fetch_fails_when_a_file_is_missing(fake_dataset):
    (fake_dataset / "olist_sellers_dataset.csv").unlink()

    with pytest.raises(FileNotFoundError, match="olist_sellers_dataset.csv"):
        download_module.fetch()
