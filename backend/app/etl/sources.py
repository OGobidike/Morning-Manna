

"""Where each translation comes from, and under what licence."""

from typing import NamedTuple

# scrollmapper/bible_databases on GitHub, pinned to one commit so every run gets the same files
COMMIT = "e1b254cef86d0e65b1a5d1a94b8b112d0f296a2c"
BASE_URL = f"https://raw.githubusercontent.com/scrollmapper/bible_databases/{COMMIT}/formats/csv"


class Source(NamedTuple):
    """One translation we load, and where its file lives."""

    code: str  # Our translation code, e.g. "KJV"
    name: str  # Full name
    license: str  # Licence, stored in the translations table
    url: str  # Where the CSV file is downloaded from


SOURCES = [
    Source("KJV", "King James Version (1769)", "Public domain", f"{BASE_URL}/KJV.csv"),
    Source("ASV", "American Standard Version (1901)", "Public domain", f"{BASE_URL}/ASV.csv"),
]
