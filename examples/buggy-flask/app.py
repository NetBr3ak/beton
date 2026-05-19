"""Tiny Flask app with one planted bug.

The planted bug is the comparison on line 13: `<=` accepts a token whose
expiry equals the current second as still valid. The fix is to tighten
it to `<` so an expiry-at-now timestamp counts as expired.

`tests/test_app.py::test_expired_token_rejected` is the regression test
that catches it.
"""
from flask import Flask, request, jsonify


def is_token_valid(now_ts: int, expiry_ts: int) -> bool:
    return now_ts <= expiry_ts  # BUG: should be `<`


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/auth/check")
    def check():
        try:
            now = int(request.args["ts"])
            expiry = int(request.args["expiry"])
        except (KeyError, ValueError):
            return jsonify({"error": "missing or invalid ts/expiry"}), 400
        return jsonify({"valid": is_token_valid(now, expiry)})

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
