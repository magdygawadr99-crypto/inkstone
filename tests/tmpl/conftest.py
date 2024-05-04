from __future__ import annotations

import pytest

from inkstone.tmpl import DictLoader, Environment


@pytest.fixture
def env():
    # no autoescaping, so expected output stays readable; the escaping tests
    # use html_env
    return Environment(autoescape=False)


@pytest.fixture
def html_env():
    return Environment(autoescape=True)


@pytest.fixture
def render(env):
    def render(source, **context):
        return env.from_string(source).render(**context)

    return render


@pytest.fixture
def make_env():
    def make_env(templates, **options):
        options.setdefault("autoescape", False)
        return Environment(DictLoader(templates), **options)

    return make_env
