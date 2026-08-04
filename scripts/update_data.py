from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TypeVar
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CONFIG_PATH = ROOT / "config.json"
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

T = TypeVar("T")


def retry(operation: Callable[[], T], label: str, attempts: int = 3, delay_seconds: int = 5) -> T:
    """Retry transient network operations and raise the final error."""
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:  # Network/API failures vary by provider.
            last_error = exc
            print(f"{label} failed on attempt {attempt}/{attempts}: {exc}")
            if attempt < attempts:
                time.sleep(delay_seconds * attempt)

    raise RuntimeError(f"{label} failed after {attempts} attempts") from last_error


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def fetch_market_data(config: dict) -> tuple[pd.DataFrame, dict[str, str]]:
    start_date = config["observation_start"]
    frames: list[pd.DataFrame] = []
    names: dict[str, str] = {}

    for item in config["market_tickers"]:
        symbol = item["symbol"]
        names[symbol] = item["name"]

        def download_symbol() -> pd.DataFrame:
            history = yf.Ticker(symbol).history(
                start=start_date,
                auto_adjust=False,
                actions=False,
            )

            if history.empty:
                raise RuntimeError(f"No Yahoo Finance data returned for {symbol}")

            history = history.reset_index()
            if "Date" not in history.columns:
                first_column = history.columns[0]
                history = history.rename(columns={first_column: "Date"})

            history["Date"] = pd.to_datetime(history["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
            history["Ticker"] = symbol

            if "Adj Close" not in history.columns:
                history["Adj Close"] = history["Close"]

            required_columns = [
                "Date",
                "Ticker",
                "Open",
                "High",
                "Low",
                "Close",
                "Adj Close",
                "Volume",
            ]
            missing = [column for column in required_columns if column not in history.columns]
            if missing:
                raise RuntimeError(f"{symbol} is missing columns: {missing}")

            history = history[required_columns].rename(columns={"Adj Close": "AdjClose"})
            numeric_columns = ["Open", "High", "Low", "Close", "AdjClose", "Volume"]
            history[numeric_columns] = history[numeric_columns].apply(pd.to_numeric, errors="coerce")
            history = history.dropna(subset=["Date", "AdjClose"])

            return history

        frames.append(retry(download_symbol, f"Yahoo Finance {symbol}"))

    market = pd.concat(frames, ignore_index=True)
    market = market.sort_values(["Ticker", "Date"]).reset_index(drop=True)
    return market, names


def fetch_fred_data(config: dict, api_key: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    observation_start = config["observation_start"]
    session = requests.Session()

    for item in config["fred_series"]:
        series_id = item["id"]
        series_name = item["name"]

        def download_series() -> pd.DataFrame:
            response = session.get(
                FRED_URL,
                params={
                    "series_id": series_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "observation_start": observation_start,
                    "sort_order": "asc",
                },
                timeout=45,
            )
            response.raise_for_status()
            payload = response.json()

            observations = payload.get("observations", [])
            if not observations:
                raise RuntimeError(f"No FRED observations returned for {series_id}")

            frame = pd.DataFrame(observations)[["date", "value"]]
            frame = frame.rename(columns={"date": "Date", "value": "Value"})
            frame["SeriesID"] = series_id
            frame["SeriesName"] = series_name
            frame["Value"] = pd.to_numeric(frame["Value"], errors="coerce")
            frame = frame.dropna(subset=["Date", "Value"])
            return frame[["Date", "SeriesID", "SeriesName", "Value"]]

        frames.append(retry(download_series, f"FRED {series_id}"))

    fred = pd.concat(frames, ignore_index=True)
    fred = fred.sort_values(["SeriesID", "Date"]).reset_index(drop=True)
    return fred


def build_snapshot(
    market: pd.DataFrame,
    market_names: dict[str, str],
    fred: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict] = []

    for symbol, group in market.groupby("Ticker", sort=False):
        group = group.sort_values("Date")
        latest = group.iloc[-1]
        previous = group.iloc[-2] if len(group) > 1 else latest

        latest_value = float(latest["AdjClose"])
        previous_value = float(previous["AdjClose"])
        change = latest_value - previous_value
        change_pct = (change / previous_value * 100.0) if previous_value else None

        rows.append(
            {
                "Source": "Yahoo",
                "SeriesID": symbol,
                "Name": market_names.get(symbol, symbol),
                "LatestDate": latest["Date"],
                "LatestValue": latest_value,
                "PreviousValue": previous_value,
                "Change": change,
                "ChangePct": change_pct,
            }
        )

    for series_id, group in fred.groupby("SeriesID", sort=False):
        group = group.sort_values("Date")
        latest = group.iloc[-1]
        previous = group.iloc[-2] if len(group) > 1 else latest

        latest_value = float(latest["Value"])
        previous_value = float(previous["Value"])
        change = latest_value - previous_value
        change_pct = (change / previous_value * 100.0) if previous_value else None

        rows.append(
            {
                "Source": "FRED",
                "SeriesID": series_id,
                "Name": latest["SeriesName"],
                "LatestDate": latest["Date"],
                "LatestValue": latest_value,
                "PreviousValue": previous_value,
                "Change": change,
                "ChangePct": change_pct,
            }
        )

    return pd.DataFrame(rows)


def atomic_csv(frame: pd.DataFrame, destination: Path) -> None:
    temp_path = destination.with_suffix(destination.suffix + ".tmp")
    frame.to_csv(temp_path, index=False)
    temp_path.replace(destination)


def atomic_json(payload: dict, destination: Path) -> None:
    temp_path = destination.with_suffix(destination.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(destination)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    api_key = os.getenv("FRED_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError(
            "FRED_API_KEY is missing. Add it as a GitHub Actions repository secret "
            "or set it in your local environment."
        )

    config = load_config()
    market, market_names = fetch_market_data(config)
    fred = fetch_fred_data(config, api_key)
    snapshot = build_snapshot(market, market_names, fred)

    updated_at = datetime.now(timezone.utc)
    metadata = {
        "updated_at_utc": updated_at.isoformat(),
        "updated_at_new_york": updated_at.astimezone(ZoneInfo("America/New_York")).isoformat(),
        "market_rows": int(len(market)),
        "fred_rows": int(len(fred)),
        "status": "success",
    }

    # Files are only replaced after every configured API call succeeds.
    atomic_csv(market, DATA_DIR / "market_data.csv")
    atomic_csv(fred, DATA_DIR / "fred_data.csv")
    atomic_csv(snapshot, DATA_DIR / "latest_snapshot.csv")
    atomic_json(metadata, DATA_DIR / "last_updated.json")

    print(
        f"Update complete: {len(market):,} market rows, "
        f"{len(fred):,} FRED rows, {len(snapshot):,} snapshot rows."
    )


if __name__ == "__main__":
    main()
