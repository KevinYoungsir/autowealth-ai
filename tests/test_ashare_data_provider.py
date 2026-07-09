import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.modules["yfinance"] = MagicMock()

import pandas as pd
import pytest

from autowealth.data.ashare_provider import AShareDataProvider
from autowealth.data.cache import ParquetCache
from autowealth.data.index_provider import AShareIndexProvider
from autowealth.data.schema import MARKET_DATA_COLUMNS, normalize_market_data


def make_mock_akshare_daily(rows=5):
    return pd.DataFrame(
        {
            "日期": pd.date_range("2024-01-02", periods=rows, freq="B").strftime("%Y-%m-%d"),
            "开盘": [10.0 + i for i in range(rows)],
            "收盘": [10.5 + i for i in range(rows)],
            "最高": [11.0 + i for i in range(rows)],
            "最低": [9.5 + i for i in range(rows)],
            "成交量": [100000 + i for i in range(rows)],
            "成交额": [1000000 + i for i in range(rows)],
            "振幅": [2.0 for _ in range(rows)],
            "涨跌幅": [1.0 for _ in range(rows)],
            "涨跌额": [0.1 for _ in range(rows)],
            "换手率": [0.5 for _ in range(rows)],
        }
    )


def test_600519_can_fetch_historical_data_with_explicit_dates():
    ak = MagicMock()
    ak.stock_zh_a_hist.return_value = make_mock_akshare_daily()
    provider = AShareDataProvider(akshare_module=ak)

    result = provider.get_daily("600519", "20090101", "2024-12-31", adjust="qfq")

    assert list(result.columns) == MARKET_DATA_COLUMNS
    assert not result.empty
    call = ak.stock_zh_a_hist.call_args.kwargs
    assert call["symbol"] == "600519"
    assert call["period"] == "daily"
    assert call["start_date"] == "20090101"
    assert call["end_date"] == "20241231"
    assert call["adjust"] == "qfq"


def test_000001_can_fetch_historical_data_without_adjustment():
    ak = MagicMock()
    ak.stock_zh_a_hist.return_value = make_mock_akshare_daily()
    provider = AShareDataProvider(akshare_module=ak)

    result = provider.get_daily("000001.SZ", "2009-01-01", "2024-12-31", adjust="none")

    assert list(result.columns) == MARKET_DATA_COLUMNS
    assert not result.empty
    call = ak.stock_zh_a_hist.call_args.kwargs
    assert call["symbol"] == "000001"
    assert call["start_date"] == "20090101"
    assert call["end_date"] == "20241231"
    assert call["adjust"] == ""


def test_index_provider_can_fetch_supported_index():
    ak = MagicMock()
    ak.index_zh_a_hist.return_value = make_mock_akshare_daily()
    provider = AShareIndexProvider(akshare_module=ak)

    result = provider.get_daily("沪深300", "2010-01-01", "2024-12-31")

    assert list(result.columns) == MARKET_DATA_COLUMNS
    assert not result.empty
    call = ak.index_zh_a_hist.call_args.kwargs
    assert call["symbol"] == "000300"
    assert call["period"] == "daily"


def test_cache_can_write_and_read(tmp_path):
    pytest.importorskip("pyarrow")
    cache = ParquetCache(cache_dir=tmp_path)
    df = normalize_market_data(make_mock_akshare_daily())

    path = cache.write(df, "600519", "2024-01-01", "2024-01-31", "qfq")
    loaded = cache.read("600519", "20240101", "20240131", "qfq")

    assert path.exists()
    assert cache.exists("600519", "2024-01-01", "2024-01-31", "qfq")
    pd.testing.assert_frame_equal(df, loaded)


def test_schema_fields_are_unified_when_source_fields_are_missing():
    raw = pd.DataFrame(
        {
            "日期": ["2024-01-02"],
            "开盘": [10],
            "最高": [11],
            "最低": [9],
            "收盘": [10.5],
        }
    )

    result = normalize_market_data(raw)

    assert list(result.columns) == MARKET_DATA_COLUMNS
    assert pd.isna(result.loc[0, "volume"])
    assert pd.isna(result.loc[0, "amount"])

