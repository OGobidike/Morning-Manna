"""The page: every persona's tiles and charts build, and the server answers. Run after dbt build."""

import os

import pytest
from sqlalchemy import create_engine

import app as dashboard
import data

URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")


@pytest.fixture(scope="module")
def engine():
    return create_engine(URL)


@pytest.mark.parametrize("persona", list(data.PERSONAS))
def test_every_persona_draws(engine, persona):
    # "app" too: CI's warehouse has no real app users, and an empty choice must not break
    tiles, *figures = dashboard.panels(engine, persona)
    assert len(tiles) == 4
    assert len(figures) == len(dashboard.PANELS) - 1
    for figure in figures:
        assert figure.layout.title.text  # every chart says what it shows


def test_charts_have_data_for_everyone(engine):
    tiles, *figures = dashboard.panels(engine, "all")
    assert all(figure.data for figure in figures)


def test_the_page_builds_and_serves(engine):
    client = dashboard.create_app(engine).server.test_client()
    page = client.get("/")
    assert page.status_code == 200
    assert b"Morning Manna dashboard" in page.data
    # The layout is built when the browser asks for it, from the warehouse
    layout = client.get("/_dash-layout")
    assert layout.status_code == 200
    assert b"Reading dashboard" in layout.data
    assert b"The reading clock" in layout.data
