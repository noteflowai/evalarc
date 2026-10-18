from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption("--target", required=True, help="folder with the code to analyze")


@pytest.fixture
def target(request) -> Path:
    path = Path(request.config.getoption("--target")).resolve()
    if not path.is_dir():
        pytest.fail(f"--target {path} is not a folder")
    return path
