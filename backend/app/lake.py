

"""A copy of every event batch in the data lake (S3), for the analytics pipeline.

The lake is a copy: Postgres stays the app's record. If the lake can't be reached, the
events are still stored and the reader never notices; a warning goes to the logs instead.

Each batch becomes one file, filed by the day it arrived:
    events/dt=2026-10-28/app-<random id>.jsonl      one JSON object per line
"""

import json
import uuid
from datetime import UTC, datetime

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import settings
from app.logs import logger
from app.models import Event

# The answers an S3 server gives when the bucket we asked for already exists
ALREADY_THERE = ("BucketAlreadyOwnedByYou", "BucketAlreadyExists")

# Set once the bucket is known to exist, so it's only checked once per server start
_bucket_ready = False


def utc_text(moment: datetime) -> str:
    """A moment as "2026-10-28T05:31:12Z", the same form the pretend readers use."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def lake_records(events: list[Event], received_at: datetime) -> list[dict]:
    """Stored events in the lake's format (the same fields as ml/simulate.py writes)."""
    return [
        {
            "event_id": f"app-{event.id}",
            "user_key": f"app:{event.user_id}",
            "event_type": event.event_type,
            "occurred_at": utc_text(event.occurred_at),
            "received_at": utc_text(received_at),
            "properties": event.properties,
            "source": "app",
        }
        for event in events
    ]


def lake_client():
    """An S3 client for the lake: SeaweedFS on this computer, or Amazon S3 later."""
    return boto3.client(
        "s3",
        endpoint_url=settings.lake_url,
        aws_access_key_id=settings.lake_access_key,
        aws_secret_access_key=settings.lake_secret_key,
        region_name="us-east-1",
        # Short timeouts and one retry: a slow lake must not hold up the server
        config=Config(
            s3={"addressing_style": "path"},
            connect_timeout=2,
            read_timeout=5,
            retries={"max_attempts": 2},
        ),
    )


def ensure_bucket(client) -> None:
    """Create the lake's bucket if it isn't there yet.

    Some S3 servers (SeaweedFS among them) leave buckets out of their bucket list, so don't
    trust the list: ask to create it, and take "you already have it" as success.
    """
    try:
        client.create_bucket(Bucket=settings.lake_bucket)
    except ClientError as error:
        if error.response["Error"]["Code"] not in ALREADY_THERE:
            raise


def save_events(records: list[dict], received_at: datetime) -> None:
    """Write one batch to the lake. Never raises: a lake problem is logged, not passed on."""
    global _bucket_ready
    if not settings.lake_url or not records:
        return  # no lake set up (e.g. in tests), or nothing to save

    key = f"events/dt={received_at:%Y-%m-%d}/app-{uuid.uuid4().hex}.jsonl"
    body = "".join(json.dumps(record) + "\n" for record in records)
    try:
        client = lake_client()
        if not _bucket_ready:
            ensure_bucket(client)
            _bucket_ready = True
        client.put_object(
            Bucket=settings.lake_bucket,
            Key=key,
            Body=body.encode(),
            ContentType="application/x-ndjson",
        )
    except Exception as error:  # the lake is only a copy: never break the app over it
        logger.warning("lake write failed", extra={"error": f"{type(error).__name__}: {error}"})
