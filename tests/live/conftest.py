"""Live probes against the real datos.gov.co (docs/09 section 9).

They hit the network, so the default ``pytest`` skips them (R-16). Run them
on purpose with::

    KOGNIA_LIVE=1 pytest tests/live -m live --durations=0

They use the real ``SocrataClient``, ``data/lexicon.json`` and
``IpsToolService`` -- no HTTP server, no paid provider, no credential besides
the optional datos.gov.co app token read through ``config`` (R-05).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from config import get_settings
from integrations.datasets.socrata_client import SocrataClient
from services.ips.lexicon import Lexicon
from services.ips.tools import IpsToolService

LIVE_DIR = Path(__file__).resolve().parent
ENABLED = os.environ.get("KOGNIA_LIVE") == "1"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: llama a datos.gov.co real; solo con KOGNIA_LIVE=1")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip = pytest.mark.skip(reason="prueba en vivo: exporta KOGNIA_LIVE=1 para correrla")
    for item in items:
        if LIVE_DIR in Path(str(item.path)).resolve().parents:
            item.add_marker(pytest.mark.live)
            if not ENABLED:
                item.add_marker(skip)


@pytest.fixture
async def live_tools():
    s = get_settings()
    client = SocrataClient(base_url=s.dataset_base_url, dataset_id=s.dataset_id, app_token=s.datos_gov_app_token,
                           connect_timeout_s=s.dataset_connect_timeout_s, read_timeout_s=s.dataset_read_timeout_s)
    svc = IpsToolService(client, Lexicon.load(s.lexicon_path), dataset_id=s.dataset_id,
                         source_url=f"{s.dataset_base_url}/resource/{s.dataset_id}.json",
                         cursor_key=b"live-probe-cursor-key-0123456789", deadline_s=s.tool_deadline_s)
    yield svc
    await client.aclose()
