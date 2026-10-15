

"""Extract: download each source file into data/raw/ (once), then read it."""

from pathlib import Path
from urllib.request import urlretrieve

import pandas as pd

from app.etl.sources import Source

# <repo root>/data/raw  (this file is backend/app/etl/extract.py, three folders down)
RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"


def download(source: Source) -> Path:
    """Download the source file unless we already have it, and return its path."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{source.code}.csv"
    if not path.exists():
        print(f"Downloading {source.code} from {source.url}")
        # Download to a temporary name first, so a broken download never looks finished
        partial = path.with_suffix(".part")
        urlretrieve(source.url, partial)
        partial.replace(path)
    return path


def extract(source: Source) -> pd.DataFrame:
    """Return the raw rows for one translation, with every column read as text."""
    path = download(source)
    return pd.read_csv(path, dtype=str, keep_default_na=False)
