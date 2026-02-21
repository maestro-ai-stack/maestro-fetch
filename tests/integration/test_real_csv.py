"""Integration tests: fetch and parse real CSV files from the internet.

No mocks. Each test downloads a real CSV, parses it via DocAdapter,
and verifies structure, column names, row counts, and sample values.

Requires network access; all tests are marked with @pytest.mark.network.
"""
from __future__ import annotations

import pytest

from maestro_fetch.adapters.doc import DocAdapter
from maestro_fetch.core.config import FetchConfig
from maestro_fetch.core.fetcher import Fetcher

network = pytest.mark.network

# ---------------------------------------------------------------------------
# Public CSV URLs (stable, well-known datasets)
# ---------------------------------------------------------------------------
IRIS_RDATASETS_URL = (
    "https://vincentarelbundock.github.io/Rdatasets/csv/datasets/iris.csv"
)
BOSTON_HOUSING_URL = (
    "https://raw.githubusercontent.com/selva86/datasets/master/BostonHousing.csv"
)
SEABORN_IRIS_URL = (
    "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/iris.csv"
)
COVID_AGGREGATED_URL = (
    "https://raw.githubusercontent.com/datasets/covid-19/main/data/"
    "countries-aggregated.csv"
)


@network
class TestIrisRdatasets:
    """Iris dataset from Rdatasets (has row-number column + header)."""

    @pytest.mark.asyncio
    async def test_fetch_and_parse(self, tmp_path):
        adapter = DocAdapter()
        config = FetchConfig(cache_dir=tmp_path, timeout=30)
        result = await adapter.fetch(IRIS_RDATASETS_URL, config)

        # Source type
        assert result.source_type == "doc"

        # Tables
        assert len(result.tables) >= 1
        df = result.tables[0]

        # Columns (Rdatasets iris has: unnamed row-index, Sepal.Length, etc.)
        assert "Sepal.Length" in df.columns
        assert "Species" in df.columns

        # Row count: exactly 150 observations
        assert len(df) == 150

        # Raw file on disk
        assert result.raw_path is not None
        assert result.raw_path.exists()
        assert result.raw_path.stat().st_size > 0

    @pytest.mark.asyncio
    async def test_species_values(self, tmp_path):
        """Verify the three species appear in the dataset."""
        adapter = DocAdapter()
        config = FetchConfig(cache_dir=tmp_path, timeout=30)
        result = await adapter.fetch(IRIS_RDATASETS_URL, config)

        df = result.tables[0]
        species = set(df["Species"].unique())
        assert species == {"setosa", "versicolor", "virginica"}

    @pytest.mark.asyncio
    async def test_first_row_values(self, tmp_path):
        """Spot-check the first data row (classic iris row 1)."""
        adapter = DocAdapter()
        config = FetchConfig(cache_dir=tmp_path, timeout=30)
        result = await adapter.fetch(IRIS_RDATASETS_URL, config)

        row0 = result.tables[0].iloc[0]
        assert float(row0["Sepal.Length"]) == pytest.approx(5.1, abs=0.01)
        assert row0["Species"] == "setosa"


@network
class TestBostonHousing:
    """Boston Housing dataset -- 506 rows, 14 numeric columns."""

    EXPECTED_COLUMNS = [
        "crim", "zn", "indus", "chas", "nox", "rm",
        "age", "dis", "rad", "tax", "ptratio", "b", "lstat", "medv",
    ]

    @pytest.mark.asyncio
    async def test_fetch_and_parse(self, tmp_path):
        adapter = DocAdapter()
        config = FetchConfig(cache_dir=tmp_path, timeout=30)
        result = await adapter.fetch(BOSTON_HOUSING_URL, config)

        assert result.source_type == "doc"
        assert len(result.tables) >= 1

        df = result.tables[0]
        for col in self.EXPECTED_COLUMNS:
            assert col in df.columns, f"Missing column: {col}"

        assert len(df) == 506

        # Raw file
        assert result.raw_path is not None
        assert result.raw_path.exists()
        assert result.raw_path.stat().st_size > 0

    @pytest.mark.asyncio
    async def test_column_count(self, tmp_path):
        adapter = DocAdapter()
        config = FetchConfig(cache_dir=tmp_path, timeout=30)
        result = await adapter.fetch(BOSTON_HOUSING_URL, config)

        assert len(result.tables[0].columns) == 14

    @pytest.mark.asyncio
    async def test_first_row_crim(self, tmp_path):
        """First row crim value is 0.00632 (well-known)."""
        adapter = DocAdapter()
        config = FetchConfig(cache_dir=tmp_path, timeout=30)
        result = await adapter.fetch(BOSTON_HOUSING_URL, config)

        first_crim = float(result.tables[0].iloc[0]["crim"])
        assert first_crim == pytest.approx(0.00632, abs=0.0001)


@network
class TestSeabornIris:
    """Seaborn iris dataset -- snake_case column names, 150 rows."""

    @pytest.mark.asyncio
    async def test_fetch_and_parse(self, tmp_path):
        adapter = DocAdapter()
        config = FetchConfig(cache_dir=tmp_path, timeout=30)
        result = await adapter.fetch(SEABORN_IRIS_URL, config)

        assert result.source_type == "doc"
        assert len(result.tables) >= 1

        df = result.tables[0]
        expected_cols = [
            "sepal_length", "sepal_width",
            "petal_length", "petal_width", "species",
        ]
        for col in expected_cols:
            assert col in df.columns

        assert len(df) == 150

        assert result.raw_path is not None
        assert result.raw_path.exists()
        assert result.raw_path.stat().st_size > 0

    @pytest.mark.asyncio
    async def test_numeric_ranges(self, tmp_path):
        """Sepal length should be in a reasonable range for iris."""
        adapter = DocAdapter()
        config = FetchConfig(cache_dir=tmp_path, timeout=30)
        result = await adapter.fetch(SEABORN_IRIS_URL, config)

        sl = result.tables[0]["sepal_length"]
        assert sl.min() >= 4.0
        assert sl.max() <= 8.0


@network
class TestCovidAggregated:
    """COVID-19 countries-aggregated dataset -- large, date-indexed."""

    @pytest.mark.asyncio
    async def test_fetch_and_parse(self, tmp_path):
        adapter = DocAdapter()
        config = FetchConfig(cache_dir=tmp_path, timeout=60)
        result = await adapter.fetch(COVID_AGGREGATED_URL, config)

        assert result.source_type == "doc"
        assert len(result.tables) >= 1

        df = result.tables[0]
        expected_cols = ["Date", "Country", "Confirmed", "Recovered", "Deaths"]
        for col in expected_cols:
            assert col in df.columns

        # Large dataset: at least 10,000 rows
        assert len(df) >= 10_000

        assert result.raw_path is not None
        assert result.raw_path.exists()
        assert result.raw_path.stat().st_size > 0

    @pytest.mark.asyncio
    async def test_contains_known_countries(self, tmp_path):
        """Dataset should contain major countries."""
        adapter = DocAdapter()
        config = FetchConfig(cache_dir=tmp_path, timeout=60)
        result = await adapter.fetch(COVID_AGGREGATED_URL, config)

        countries = set(result.tables[0]["Country"].unique())
        for name in ["US", "China", "Brazil", "India"]:
            assert name in countries, f"Missing country: {name}"


@network
class TestFetcherRoutesCSV:
    """Verify Fetcher dispatches CSV URLs to DocAdapter, not WebAdapter."""

    @pytest.mark.asyncio
    async def test_fetcher_routes_csv_to_doc(self, tmp_path):
        fetcher = Fetcher()
        config = FetchConfig(cache_dir=tmp_path, timeout=30)
        result = await fetcher.fetch(SEABORN_IRIS_URL, config)

        # Must be handled by DocAdapter (source_type == "doc")
        assert result.source_type == "doc"
        assert len(result.tables) >= 1
        assert "sepal_length" in result.tables[0].columns
        assert len(result.tables[0]) == 150
