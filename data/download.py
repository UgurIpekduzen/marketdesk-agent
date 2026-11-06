"""Download the Olist Brazilian E-Commerce dataset into data/raw/.

The dataset is public, so no Kaggle account or API key is needed.
Licence: CC BY-NC-SA 4.0. The files stay local: data/ is gitignored.
"""

import shutil
from pathlib import Path

import kagglehub

# Pinned to a dataset version so every machine loads the same rows.
DATASET = "olistbr/brazilian-ecommerce/versions/2"
RAW_DIR = Path(__file__).parent / "raw"
EXPECTED_FILES = (
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
)


def fetch(output_dir: Path | None = None) -> Path:
    """Fetch the dataset and return the folder that holds its CSV files.

    Without output_dir the files land in kagglehub's cache; with it they
    are written straight into that folder.
    """
    target = None if output_dir is None else str(output_dir)
    source = Path(kagglehub.dataset_download(DATASET, output_dir=target))
    missing = [name for name in EXPECTED_FILES if not (source / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"Dataset is missing expected files: {', '.join(missing)}"
        )
    return source


def download(raw_dir: Path = RAW_DIR) -> Path:
    """Fetch the dataset and copy its CSV files into raw_dir."""
    source = fetch()
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name in EXPECTED_FILES:
        shutil.copy2(source / name, raw_dir / name)
    return raw_dir


if __name__ == "__main__":
    target = download()
    print(f"Olist dataset ready in {target} ({len(EXPECTED_FILES)} files)")
