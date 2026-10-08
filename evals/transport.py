"""Reproducible HTTP fixture transport through the real FastAPI routes."""
from contextlib import contextmanager
from unittest.mock import patch
from urllib.parse import urlsplit

import requests
from fastapi.testclient import TestClient
from mock_api.app import app


@contextmanager
def vendor_transport(mode: str):
    if mode == "http":
        yield
        return
    with TestClient(app) as client:
        def get(url, **kwargs):
            response = client.get(urlsplit(url).path)
            result = requests.Response()
            result.status_code = response.status_code
            result._content = response.content
            return result
        with patch("src.vendor_client.requests.get", get):
            yield
