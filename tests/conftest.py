"""Exercise the real vendor HTTP handler without a listening server or network."""
import pytest
import requests
from fastapi.testclient import TestClient
from urllib.parse import urlsplit

from mock_api.app import app


@pytest.fixture(autouse=True)
def isolated_vendor_api(monkeypatch):
    monkeypatch.setenv("VENDOR_RISK_BASE_URL", "http://vendor.test")
    with TestClient(app) as client:
        def get(url, **kwargs):
            parsed = urlsplit(url)
            if parsed.hostname != "vendor.test":
                raise AssertionError(f"Unexpected network access in test: {parsed.hostname}")
            response = client.get(parsed.path)
            # Adapt httpx's response to requests' interface used by the client.
            result = requests.Response()
            result.status_code = response.status_code
            result._content = response.content
            return result
        monkeypatch.setattr(requests, "get", get)
        yield
