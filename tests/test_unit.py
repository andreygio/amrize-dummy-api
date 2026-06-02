import pytest

from app.main import app as flask_app


@pytest.fixture()
def app():
    flask_app.config["TESTING"] = True
    yield flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


class TestInfoEndpoint:
    def test_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_returns_json_content_type(self, client):
        response = client.get("/")
        assert response.content_type == "application/json"

    def test_response_has_required_keys(self, client):
        data = client.get("/").get_json()
        assert {"application", "environment", "version"} <= data.keys()

    def test_default_application_name(self, client):
        data = client.get("/").get_json()
        assert isinstance(data["application"], str)
        assert len(data["application"]) > 0

    def test_default_environment(self, client):
        data = client.get("/").get_json()
        assert isinstance(data["environment"], str)

    def test_default_version(self, client):
        data = client.get("/").get_json()
        assert isinstance(data["version"], str)


class TestHealthEndpoint:
    def test_returns_200(self, client):
        assert client.get("/health").status_code == 200

    def test_returns_status_ok(self, client):
        data = client.get("/health").get_json()
        assert data == {"status": "ok"}

    def test_returns_json_content_type(self, client):
        response = client.get("/health")
        assert response.content_type == "application/json"


class TestEnvVarOverrides:
    def test_application_name_from_env(self, monkeypatch, client):
        import app.main as m

        monkeypatch.setattr(m, "APPLICATION_NAME", "custom-app")
        data = client.get("/").get_json()
        assert data["application"] == "custom-app"

    def test_environment_from_env(self, monkeypatch, client):
        import app.main as m

        monkeypatch.setattr(m, "ENVIRONMENT", "staging")
        data = client.get("/").get_json()
        assert data["environment"] == "staging"

    def test_version_from_env(self, monkeypatch, client):
        import app.main as m

        monkeypatch.setattr(m, "VERSION", "2.5.0")
        data = client.get("/").get_json()
        assert data["version"] == "2.5.0"
