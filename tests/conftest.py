import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tests.gen.samples import build_sample_set  # noqa: E402


@pytest.fixture(scope="session")
def sample_set(tmp_path_factory):
    d = tmp_path_factory.mktemp("samples")
    truth = build_sample_set(str(d))
    return str(d), truth


@pytest.fixture(scope="session")
def records(sample_set):
    import fapiao_kit
    d, truth = sample_set
    return {r.key: r for r in fapiao_kit.scan(d, truth["rules"])}
