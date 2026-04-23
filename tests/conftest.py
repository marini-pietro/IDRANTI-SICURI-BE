"""
Shared pytest fixtures for the backend test suite.
"""

from api_server import main_api
import pytest


@pytest.fixture
def client():
    """Return a Flask test client for the application."""
    return main_api.test_client()
