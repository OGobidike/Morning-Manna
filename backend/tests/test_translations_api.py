

"""Tests for GET /translations."""

from app.models import Translation


def test_lists_translations_by_code(client, db):
    db.add(Translation(code="ZZ1", name="Test Translation One", license="Public domain"))
    db.flush()

    response = client.get("/translations")

    assert response.status_code == 200
    assert {"code": "ZZ1", "name": "Test Translation One"} in response.json()
    codes = [translation["code"] for translation in response.json()]
    assert codes == sorted(codes)


def test_only_code_and_name_are_shown(client, db):
    db.add(Translation(code="ZZ2", name="Test Translation Two", license="Public domain"))
    db.flush()

    for translation in client.get("/translations").json():
        assert set(translation) == {"code", "name"}
