

"""Where the lake and the warehouse are. Read from environment variables, with local defaults."""

import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

# The answers an S3 server gives when the bucket we asked for already exists
ALREADY_THERE = ("BucketAlreadyOwnedByYou", "BucketAlreadyExists")


def lake_bucket() -> str:
    return os.environ.get("LAKE_BUCKET", "morning-manna-lake")


def lake_client():
    """An S3 client for the lake: SeaweedFS from docker compose, or Amazon S3 later."""
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("LAKE_URL", "http://localhost:8333"),
        aws_access_key_id=os.environ.get("LAKE_ACCESS_KEY", "lake"),
        aws_secret_access_key=os.environ.get("LAKE_SECRET_KEY", "lake-secret"),
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )


def database_url() -> str:
    """The warehouse: the same Postgres as the app, in its own schema."""
    url = os.environ.get("DATABASE_URL", "postgresql://manna:manna@localhost:5432/manna")
    # The backend's address names SQLAlchemy's driver; plain psycopg doesn't want that part
    return url.replace("postgresql+psycopg://", "postgresql://")


def ensure_bucket(client, bucket: str) -> None:
    """Create the bucket if it isn't there yet.

    Some S3 servers (SeaweedFS among them) leave buckets out of their bucket list, so don't
    trust the list: ask to create it, and take "you already have it" as success.
    """
    try:
        client.create_bucket(Bucket=bucket)
    except ClientError as error:
        if error.response["Error"]["Code"] not in ALREADY_THERE:
            raise
