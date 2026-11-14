
"""Market-data provider abstraction. Historical daily data only."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx


class ProviderUnavailable(RuntimeError):
    pass


class AlphaVantageProvider:
    BASE = "https://www.alphavantage.co/query"

    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY")

    async def daily(self, symbol: str):
        if not self.api_key:
            raise ProviderUnavailable(
                "Alpha Vantage API key is not configured."
            )

        currencies = {
            "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD",
            "NZD", "ZAR", "CNY", "HKD", "SGD", "MXN", "BRL",
            "NOK", "SEK", "DKK", "PLN", "TRY", "INR", "KRW"
        }

        is_fx = (
            len(symbol) == 6
            and symbol[:3] in currencies
            and symbol[3:] in currencies
        )

        if is_fx:
            params = {
                "function": "FX_DAILY",
                "from_symbol": symbol[:3],
                "to_symbol": symbol[3:],
                "outputsize": "compact",
                "apikey": self.api_key
            }
        else:
            params = {
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol,
                "outputsize": "compact",
                "apikey": self.api_key
            }

        try:
            async with httpx.AsyncClient(
                timeout=20,
                headers={"User-Agent": "MarketMindAI/0.2"}
            ) as client:
                response = await client.get(self.BASE, params=params)
                response.raise_for_status()
                payload = response.json()

        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailable(
                f"Alpha Vantage request failed: {type(exc).__name__}"
            ) from exc

        series = (
            payload.get("Time Series FX (Daily)")
            if is_fx
            else payload.get("Time Series (Daily)")
        )

        if not series:
            message = (
                payload.get("Note")
                or payload.get("Information")
                or payload.get("Error Message")
                or "No daily price history returned."
            )
            raise ProviderUnavailable(str(message)[:240])

        rows = []

        try:
            for day, values in sorted(series.items()):
                rows.append({
                    "date": day,
                    "open": float(values["1. open"]),
                    "high": float(values["2. high"]),
                    "low": float(values["3. low"]),
                    "close": float(values["4. close"]),
                    "volume": (
                        None if is_fx
                        else int(float(values["5. volume"]))
                    )
                })
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderUnavailable(
                "Alpha Vantage returned an unexpected candle format."
            ) from exc

        return {
            "symbol": symbol.upper(),
            "instrument_type": "forex" if is_fx else "equity_or_etf",
            "provider": "Alpha Vantage",
            "status": "end_of_day_or_historical",
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "last_bar_date": rows[-1]["date"] if rows else None,
            "candles": rows
        }


class TwelveDataProvider:
    BASE = "https://api.twelvedata.com/time_series"

    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY")

    async def daily(self, symbol: str):
        if not self.api_key:
            raise ProviderUnavailable(
                "Twelve Data API key is not configured."
            )

        currencies = {
            "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD",
            "NZD", "ZAR", "CNY", "HKD", "SGD", "MXN", "BRL",
            "NOK", "SEK", "DKK", "PLN", "TRY", "INR", "KRW"
        }

        is_fx = (
            len(symbol) == 6
            and symbol[:3] in currencies
            and symbol[3:] in currencies
        )

        provider_symbol = (
            f"{symbol[:3]}/{symbol[3:]}" if is_fx else symbol
        )

        params = {
            "symbol": provider_symbol,
            "interval": "1day",
            "outputsize": 5000,
            "order": "asc",
            "apikey": self.api_key
        }

        try:
            async with httpx.AsyncClient(
                timeout=25,
                headers={"User-Agent": "MarketMindAI/0.2"}
            ) as client:
                response = await client.get(self.BASE, params=params)
                response.raise_for_status()
                payload = response.json()

        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            detail = exc.response.text[:300]

            detail = detail.replace(self.api_key, "[REDACTED]")

            raise ProviderUnavailable(
                f"Twelve Data HTTP {status_code}: {detail}"
            ) from exc

        except httpx.RequestError as exc:
            raise ProviderUnavailable(
                f"Twelve Data network error: {type(exc).__name__}"
            ) from exc

        except ValueError as exc:
            raise ProviderUnavailable(
                "Twelve Data returned invalid JSON."
            ) from exc

        values = payload.get("values")

        if not values or payload.get("status") == "error":
            message = payload.get(
                "message",
                "Twelve Data returned no daily price history."
            )
            raise ProviderUnavailable(str(message)[:240])

        rows = []

        try:
            for item in values:
                volume = item.get("volume")

                rows.append({
                    "date": item["datetime"][:10],
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": (
                        int(float(volume))
                        if volume not in (None, "")
                        else None
                    )
                })

        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderUnavailable(
                "Twelve Data returned an unexpected candle format."
            ) from exc

        rows.sort(key=lambda item: item["date"])

        if not rows:
            raise ProviderUnavailable(
                "No usable daily candles returned."
            )

        return {
            "symbol": symbol.upper(),
            "instrument_type": "forex" if is_fx else "equity_or_etf",
            "provider": "Twelve Data",
            "status": "end_of_day_or_historical",
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "last_bar_date": rows[-1]["date"],
            "candles": rows
        }
