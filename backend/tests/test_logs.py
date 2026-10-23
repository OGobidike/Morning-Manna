

"""Tests for structured request logs."""

import json
import logging

import pytest

from app.logs import JsonFormatter


@pytest.fixture
def request_logs(caplog):
    """Capture our app's log records during a test."""
    caplog.set_level(logging.INFO, logger="morning_manna")
    return caplog


def logged_paths(caplog):
    return [record.path for record in caplog.records if hasattr(record, "path")]


def test_every_request_is_logged(client, request_logs):
    client.get("/health")

    record = next(r for r in request_logs.records if getattr(r, "path", None) == "/health")
    assert record.method == "GET"
    assert record.status == 200
    assert record.duration_ms >= 0


def test_failed_requests_are_logged_with_their_status(client, request_logs):
    client.get("/users/me")

    record = next(r for r in request_logs.records if getattr(r, "path", None) == "/users/me")
    assert record.status == 401


def test_a_log_line_is_one_json_object():
    record = logging.LogRecord("morning_manna", logging.INFO, __file__, 1, "request", None, None)
    record.method, record.path, record.status, record.duration_ms = "GET", "/health", 200, 1.5

    line = JsonFormatter().format(record)

    entry = json.loads(line)
    assert entry["message"] == "request"
    assert entry["level"] == "INFO"
    assert entry["path"] == "/health"
    assert entry["status"] == 200
    assert "time" in entry


def test_tokens_never_reach_the_logs(client, headers, request_logs):
    token = headers["Authorization"].removeprefix("Bearer ")

    client.get("/users/me?token=" + token, headers=headers)

    lines = [JsonFormatter().format(record) for record in request_logs.records]
    assert "/users/me" in logged_paths(request_logs)
    assert not any(token in line for line in lines)
