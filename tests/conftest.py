"""Fixtures. The server fixtures are a real jlr-server response from a 2020 I-Pace (November 2026) with the VIN and
positions replaced."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
VIN = "SADHA2B10L1000001"
URL = "http://jlr.test:9293"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
