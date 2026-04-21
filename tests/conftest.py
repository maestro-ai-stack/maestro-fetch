from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="run tests marked as requiring live network access",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-network"):
        return

    skip_network = pytest.mark.skip(reason="need --run-network to run")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)

