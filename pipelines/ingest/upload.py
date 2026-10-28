

"""Copy a local lake folder (the pretend readers from ml/simulate.py) up to the S3 lake.

Run from the repo root:
    python -m ingest.upload                 # uploads data/lake
    python -m ingest.upload --from other/folder
"""

import argparse
from pathlib import Path

from ingest.settings import ensure_bucket, lake_bucket, lake_client


def upload(folder: Path, client, bucket: str) -> int:
    """Upload every .jsonl file, keeping its path: data/lake/events/dt=.../x.jsonl -> events/..."""
    ensure_bucket(client, bucket)
    count = 0
    for path in sorted(folder.rglob("*.jsonl")):
        key = path.relative_to(folder).as_posix()
        client.upload_file(str(path), bucket, key)
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a local lake folder to the S3 lake.")
    parser.add_argument("--from", dest="folder", type=Path, default=Path("data/lake"))
    args = parser.parse_args()
    if not args.folder.is_dir():
        raise SystemExit(f"{args.folder} doesn't exist: run python ml/simulate.py first")
    count = upload(args.folder, lake_client(), lake_bucket())
    print(f"Uploaded {count} files from {args.folder}/ to the lake")


if __name__ == "__main__":
    main()
