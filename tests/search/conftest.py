from __future__ import annotations

import pytest

from .corpus import build_index


@pytest.fixture(scope="session")
def index():
    return build_index()
