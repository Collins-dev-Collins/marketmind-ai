"""Market-data provider abstraction. Alpha Vantage daily history is opt-in via server env."""
from __future__ import annotations
import os
from datetime import datetime, timezone
import httpx

class ProviderUnavailable(RuntimeError): pass

class AlphaVantageProvider:
    BASE="https://www.alphavantage.co/query"
    def __init__(self, api_key=None): self.api_key=api_key or os.getenv("ALPHA_VANTAGE_API_KEY")
    async def daily(self, symbol: str):
        if not self.api_key: raise ProviderUnavailable("No market-data provider configured. Add ALPHA_VANTAGE_API_KEY on the backend; no quote is being shown as live.")
        currencies={"USD","EUR","GBP","JPY","CHF","CAD","AUD","NZD","ZAR","CNY","HKD","SGD","MXN","BRL","NOK","SEK","DKK","PLN","TRY","INR","KRW"}
        is_fx=len(symbol)==6 and symbol[:3] in currencies and symbol[3:] in currencies
        if is_fx:
            params={"function":"FX_DAILY","from_symbol":symbol[:3],"to_symbol":symbol[3:],"outputsize":"compact","apikey":self.api_key}
        else:
            params={"function":"TIME_SERIES_DAILY","symbol":symbol,"outputsize":"compact","apikey":self.api_key}
        try:
            async with httpx.AsyncClient(timeout=20,headers={"User-Agent":"MarketMindAI/0.1 educational research app"}) as client:
                response=await client.get(self.BASE,params=params); response.raise_for_status(); payload=response.json()
        except (httpx.HTTPError, ValueError) as exc: raise ProviderUnavailable(f"Market-data request failed: {type(exc).__name__}") from exc
        series=payload.get("Time Series FX (Daily)") if is_fx else payload.get("Time Series (Daily)")
        if not series:
            msg=payload.get("Note") or payload.get("Information") or payload.get("Error Message") or "Provider returned no daily series. Check symbol, provider limits, and entitlement."
            raise ProviderUnavailable(str(msg)[:240])
        rows=[]
        for day, values in sorted(series.items()):
            if is_fx:
                rows.append({"date":day,"open":float(values["1. open"]),"high":float(values["2. high"]),"low":float(values["3. low"]),"close":float(values["4. close"]),"volume":None})
            else:
                rows.append({"date":day,"open":float(values["1. open"]),"high":float(values["2. high"]),"low":float(values["3. low"]),"close":float(values["4. close"]),"volume":int(float(values["5. volume"]))})
        return {"symbol":symbol.upper(),"instrument_type":"forex" if is_fx else "equity_or_etf","provider":"Alpha Vantage","status":"end_of_day_or_historical","retrieved_at_utc":datetime.now(timezone.utc).isoformat(),"last_bar_date":rows[-1]["date"] if rows else None,"candles":rows}
