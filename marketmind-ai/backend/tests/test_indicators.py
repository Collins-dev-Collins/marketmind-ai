import pytest
from app.indicators import sma, ema, rsi, macd, bollinger, atr, analyze

def test_sma_known_value(): assert sma([1,2,3,4,5],3)==4.0
def test_sma_insufficient(): assert sma([1,2],3) is None
def test_ema_known_seed(): assert ema([1,2,3],3)==2.0
def test_rsi_all_gains(): assert rsi(list(range(1,20)),14)==100.0
def test_rsi_all_losses(): assert rsi(list(range(20,1,-1)),14)==0.0
def test_macd_requires_history(): assert macd([1,2,3]) is None
def test_bollinger_bounds():
    x=bollinger([1]*20); assert x["upper"]==x["middle"]==x["lower"]==1.0
def test_atr_known_constant_range():
    close=list(range(1,20)); high=[x+1 for x in close]; low=[x-1 for x in close]
    assert atr(high,low,close,14)==2.0
def test_analyze_does_not_make_probability():
    out=analyze(list(range(1,70)))
    assert "probability" not in out
    assert out["observations"]==69

def test_invalid_nan_rejected():
    with pytest.raises(ValueError): sma([1,float('nan')],2)

def test_macd_rising_series_is_positive():
    out=macd(list(range(1,60)))
    assert out is not None
    assert out["macd"] > 0
    assert out["histogram"] >= -1e-10

def test_macd_flat_series_is_zero():
    out=macd([5.0]*60)
    assert out is not None
    assert out["macd"] == pytest.approx(0.0)
    assert out["histogram"] == pytest.approx(0.0)
