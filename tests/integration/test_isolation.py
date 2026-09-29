"""The footgun, pinned down by tests so it cannot come back."""

from __future__ import annotations

import pytest

from config import get_settings
from integrations.db.migrations import database_name
from tests.integration.conftest import assert_is_test_database

pytestmark = pytest.mark.integration


def test_guard_refuses_the_development_database():
    with pytest.raises(RuntimeError, match="Negado"):
        assert_is_test_database(get_settings().database_url)


def test_guard_accepts_only_test_databases():
    assert_is_test_database("postgresql://u@h:5433/kognia_test")
    with pytest.raises(RuntimeError):
        assert_is_test_database("postgresql://u@h:5433/kognia")
    with pytest.raises(RuntimeError):
        assert_is_test_database("postgresql://u@h:5433/testing_kognia")


def test_tests_and_development_point_at_different_databases(test_database_url):
    assert database_name(test_database_url) != database_name(get_settings().database_url)
