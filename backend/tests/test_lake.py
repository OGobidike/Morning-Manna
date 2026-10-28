

"""Tests for the copy of event batches in the data lake, against a real local S3 server."""

import json
import logging
import socket
from datetime import UTC, datetime

import boto3
import pytest
from moto.server import ThreadedMotoServer

from app import lake
from app.config import settings


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def s3_url():
    """moto's S3 server on this machine: it speaks S3 over HTTP, like SeaweedFS or AWS."""
    port = free_port()
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=port)
    server.start()
    yield f"http://127.0.0.1:{port}"
    server.stop()


@pytest.fixture
def lake_on(s3_url, monkeypatch):
    """Point the API at the test lake, with an empty bucket each time."""
    bucket = f"test-lake-{free_port()}"
    monkeypatch.setattr(settings, "lake_url", s3_url)
    monkeypatch.setattr(settings, "lake_bucket", bucket)
    monkeypatch.setattr(lake, "_bucket_ready", False)
    return lake.lake_client(), bucket


def files_in(client, bucket) -> dict[str, list[dict]]:
    """Every file in the lake: its name, and its lines as dicts."""
    found = {}
    for item in client.list_objects_v2(Bucket=bucket).get("Contents", []):
        body = client.get_object(Bucket=bucket, Key=item["Key"])["Body"].read().decode()
        found[item["Key"]] = [json.loads(line) for line in body.splitlines()]
    return found


def send(client, headers, *events):
    return client.post("/events", json={"events": list(events)}, headers=headers)


def event(event_type="app_opened", occurred_at="2026-10-28T05:31:12+01:00", **properties):
    return {"event_type": event_type, "occurred_at": occurred_at, "properties": properties}


def test_a_batch_lands_in_the_lake_as_one_file(client, headers, lake_on):
    s3, bucket = lake_on
    response = send(client, headers, event(), event("reminder_snoozed", minutes=10))
    assert response.status_code == 201

    files = files_in(s3, bucket)
    assert len(files) == 1
    key, lines = next(iter(files.items()))
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    assert key.startswith(f"events/dt={today}/app-") and key.endswith(".jsonl")
    assert [line["event_type"] for line in lines] == ["app_opened", "reminder_snoozed"]
    assert lines[1]["properties"] == {"minutes": 10}


def test_lake_lines_match_the_pretend_readers_format(client, headers, lake_on):
    s3, bucket = lake_on
    send(client, headers, event())
    (line,) = next(iter(files_in(s3, bucket).values()))
    assert set(line) == {
        "event_id", "user_key", "event_type", "occurred_at", "received_at", "properties", "source"
    }
    assert line["source"] == "app"
    assert line["event_id"].startswith("app-") and line["user_key"].startswith("app:")
    # Stored in UTC: 05:31 in a +01:00 time zone is 04:31Z
    assert line["occurred_at"] == "2026-10-28T04:31:12Z"
    assert line["received_at"].endswith("Z")


def test_each_batch_is_its_own_file(client, headers, lake_on):
    s3, bucket = lake_on
    send(client, headers, event())
    send(client, headers, event())
    assert len(files_in(s3, bucket)) == 2


def test_a_broken_lake_never_breaks_the_app(client, headers, monkeypatch, caplog):
    # Nothing listens on this port, so every lake write fails
    monkeypatch.setattr(settings, "lake_url", f"http://127.0.0.1:{free_port()}")
    monkeypatch.setattr(lake, "_bucket_ready", False)
    with caplog.at_level(logging.WARNING, logger="morning_manna"):
        response = send(client, headers, event())
    assert response.status_code == 201 and response.json() == {"accepted": 1}
    assert any(record.getMessage() == "lake write failed" for record in caplog.records)


def test_no_lake_url_means_no_lake_at_all(client, headers, monkeypatch):
    monkeypatch.setattr(settings, "lake_url", "")

    def no_calls(*args, **kwargs):
        raise AssertionError("the lake was called although it is switched off")

    monkeypatch.setattr(boto3, "client", no_calls)
    assert send(client, headers, event()).status_code == 201
