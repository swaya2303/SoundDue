"""
tests/test_health.py
====================
Pytest test for GET /health endpoint.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200


def test_health_body():
    response = client.get("/health")
    assert response.json() == {"status": "ok"}


def test_health_content_type():
    response = client.get("/health")
    assert "application/json" in response.headers["content-type"]
