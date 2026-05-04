"""
Shared pytest fixtures for the backend test suite.
"""

import os
import sys
import pytest

# Ensure the repository root is on sys.path so test imports find application modules.
# This makes tests runnable when pytest's working directory doesn't already include
# the project root.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api_server import main_api


@pytest.fixture
def client():
    """Return a Flask test client for the application."""
    return main_api.test_client()
