"""Deterministic technical indicators. Input series must be chronological (oldest first)."""
from __future__ import annotations
import math
import numpy as np


def _arr(values):
    a = np.asarray(values, dtype=float)
    if a.ndim != 1 or not np.all(np.isfinite(a)):
        raise ValueError("Values must be a finite one-dimensional series")
    return a


def sma(values, period: int):
    a = _arr(values)
    if period < 1: raise ValueError("period must be positive")
    if len(a) < period: return None
    return float(np.mean(a[-period:]))


def ema(values, period: int):
    a = _arr(values)
    if period < 1: raise ValueError("period must be positive")
    if len(a) < period: return None
    alpha = 2 / (period + 1)
    value = float(np.mean(a[:period]))
    for x in a[period:]: value = alpha * float(x) + (1-alpha) * value
    return value


def rsi(values, period: int = 14):
    a = _arr(values)
    if period < 1: raise ValueError("period must be positive")
    if len(a) <= period: return None
    d = np.diff(a)
    gains = np.maximum(d, 0); losses = np.maximum(-d, 0)
    avg_gain = float(np.mean(gains[:period])); avg_loss = float(np.mean(losses[:period]))
    for i in range(period, len(gains)):
        avg_gain = (avg_gain*(period-1)+float(gains[i]))/period
        avg_loss = (avg_loss*(period-1)+float(losses[i]))/period
    if avg_loss == 0: return 100.0 if avg_gain > 0 else 50.0
    return 100 - (100/(1+avg_gain/avg_loss))


def macd(values, fast=12, slow=26, signal=9):
    a = _arr(values)
    if fast >= slow: raise ValueError("fast period must be less than slow period")
    if len(a) < slow + signal - 1: return None
    alpha_f=2/(fast+1); alpha_s=2/(slow+1)
    # Seed the fast EMA at `fast`, then keep updating it while the slow EMA warms up.
    f=float(np.mean(a[:fast])); s=float(np.mean(a[:slow])); line=[]
    for i in range(fast, len(a)):
        f=alpha_f*float(a[i])+(1-alpha_f)*f
        if i == slow-1:
            line.append(f-s)
        elif i >= slow:
            s=alpha_s*float(a[i])+(1-alpha_s)*s
            line.append(f-s)
    if len(line) < signal: return None
    sig=ema(line, signal)
    return {"macd": float(line[-1]), "signal": float(sig), "histogram": float(line[-1]-sig)}


def bollinger(values, period=20, deviations=2):
    a = _arr(values)
    if period < 2 or deviations <= 0: raise ValueError("invalid Bollinger parameters")
    if len(a) < period: return None
    window=a[-period:]; mid=float(np.mean(window)); sd=float(np.std(window, ddof=0))
    return {"middle":mid,"upper":mid+deviations*sd,"lower":mid-deviations*sd}


def atr(high, low, close, period=14):
    h=_arr(high); l=_arr(low); c=_arr(close)
    if not (len(h)==len(l)==len(c)): raise ValueError("OHLC arrays must have equal lengths")
    if period < 1: raise ValueError("period must be positive")
    if len(c) <= period: return None
    tr=np.maximum(h[1:]-l[1:], np.maximum(np.abs(h[1:]-c[:-1]),np.abs(l[1:]-c[:-1])))
    value=float(np.mean(tr[:period]))
    for x in tr[period:]: value=(value*(period-1)+float(x))/period
    return value


def analyze(closes, highs=None, lows=None):
    c=_arr(closes)
    result={"sma20":sma(c,20),"sma50":sma(c,50),"ema20":ema(c,20),"rsi14":rsi(c,14),
            "macd":macd(c),"bollinger20":bollinger(c),"observations":len(c)}
    if highs is not None and lows is not None: result["atr14"]=atr(highs,lows,c)
    signals=[]
    if result["sma20"] is not None and result["sma50"] is not None:
        signals.append("bullish" if result["sma20"]>result["sma50"] else "bearish")
    if result["rsi14"] is not None:
        signals.append("bearish" if result["rsi14"]>=70 else "bullish" if result["rsi14"]<=30 else "neutral")
    if result["macd"]:
        signals.append("bullish" if result["macd"]["histogram"]>0 else "bearish" if result["macd"]["histogram"]<0 else "neutral")
    if not signals: assessment="insufficient_evidence"
    else:
        score=sum(1 if s=="bullish" else -1 if s=="bearish" else 0 for s in signals)
        assessment="moderately_bullish" if score>=2 else "bullish" if score==1 else "moderately_bearish" if score<=-2 else "bearish" if score==-1 else "neutral_or_mixed"
    result["assessment"]=assessment
    result["method_note"]="Rule-based indicator summary, not a calibrated probability or investment recommendation. Indicators can conflict and lag price."
    return result
