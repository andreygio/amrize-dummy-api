import json

import pytest

from app.main import app as flask_app


@pytest.fixture()
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


class TestInfoContract:
    def test_full_response_shape(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.get_json()
        assert set(data.keys()) == {"application", "environment", "version"}

    def test_no_extra_keys(self, client):
        data = client.get("/").get_json()
        assert len(data) == 3

    def test_response_is_valid_json(self, client):
        response = client.get("/")
        assert json.loads(response.data) is not None

    def test_method_not_allowed_post(self, client):
        assert client.post("/").status_code == 405

    def test_method_not_allowed_put(self, client):
        assert client.put("/").status_code == 405


class TestHealthContract:
    def test_health_is_idempotent(self, client):
        r1 = client.get("/health").get_json()
        r2 = client.get("/health").get_json()
        assert r1 == r2

    def test_health_under_repeated_load(self, client):
        for _ in range(50):
            assert client.get("/health").status_code == 200

    def test_unknown_path_returns_404(self, client):
        assert client.get("/nonexistent").status_code == 404
