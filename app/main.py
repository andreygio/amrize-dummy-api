import os

from flask import Flask, Response, jsonify

app = Flask(__name__)

APPLICATION_NAME = os.environ.get("APPLICATION_NAME", "hello-platform")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
VERSION = os.environ.get("VERSION", "1.0.0")


@app.route("/")
def info() -> Response:
    return jsonify(
        application=APPLICATION_NAME,
        environment=ENVIRONMENT,
        version=VERSION,
    )


@app.route("/health")
def health() -> tuple[Response, int]:
    return jsonify(status="ok"), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
