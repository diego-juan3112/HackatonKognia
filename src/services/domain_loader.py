"""Load a DomainSpec from YAML.

This is the only place that reads the domain file. On challenge day the whole
adaptation can be a new YAML passed through ``DOMAIN_CONFIG_PATH``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from models.domain_config import DomainSpec


def load_domain(path: str | Path) -> DomainSpec:
    """Parse and validate the domain description at ``path``."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Domain configuration not found: {path}. "
            "Point DOMAIN_CONFIG_PATH at a valid YAML file."
        )

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return DomainSpec.model_validate(raw)
