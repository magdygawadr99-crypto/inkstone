from __future__ import annotations

import pytest

from .helpers import make_config


@pytest.fixture
def config(tmp_path):
    return make_config(tmp_path, base_url="https://example.com/")
