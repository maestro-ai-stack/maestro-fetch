import pandas as pd
from maestro_fetch.core.result import FetchResult
from maestro_fetch.core.errors import FetchError, UnsupportedURLError


def test_fetch_result_defaults():
    r = FetchResult(url="https://example.com", source_type="web", content="hello")
    assert r.tables == []
    assert r.metadata == {}
    assert r.raw_path is None


def test_fetch_result_with_table():
    df = pd.DataFrame({"a": [1, 2]})
    r = FetchResult(url="https://example.com", source_type="pdf", content="", tables=[df])
    assert len(r.tables) == 1
    assert list(r.tables[0].columns) == ["a"]


def test_error_hierarchy():
    e = UnsupportedURLError("ftp://bad")
    assert isinstance(e, FetchError)
