import pytest
from fastapi.testclient import TestClient
from app.main import app
client=TestClient(app)

def test_health(): assert client.get('/api/health').json()['status']=='ok'
def test_invalid_symbol(): assert client.get('/api/search?q=bad%20symbol').status_code==400
def test_unconfigured_market_is_honest():
    r=client.get('/api/market/TEST')
    assert r.status_code==503
    assert r.json()['detail']['data_status']=='unavailable'
def test_forex_position_size():
    r=client.post('/api/forex/position-size',json={'balance':10000,'risk_percent':1,'entry':1.1,'stop':1.09,'pip_size':0.0001,'pip_value_per_lot':10,'spread_pips':1,'commission_per_lot':7})
    assert r.status_code==200
    assert r.json()['stop_distance_pips']==pytest.approx(100)
    assert r.json()['risk_budget']==pytest.approx(100)
    assert r.json()['position_size_lots']==pytest.approx(100/1017)

def test_forex_bad_balance(): assert client.post('/api/forex/position-size',json={'balance':0,'risk_percent':1,'entry':1.1,'stop':1.09,'pip_size':.0001,'pip_value_per_lot':10,'spread_pips':1,'commission_per_lot':0}).status_code==422

def test_watchlist_create_list_delete(tmp_path, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, 'DB', tmp_path / 'test.sqlite3')
    added=client.post('/api/watchlist',json={'symbol':'AAPL'})
    assert added.status_code==200 and added.json()['saved'] is True
    listed=client.get('/api/watchlist').json()['items']
    assert any(x['symbol']=='AAPL' for x in listed)
    removed=client.delete('/api/watchlist/AAPL')
    assert removed.status_code==200 and removed.json()['removed'] is True
    assert all(x['symbol']!='AAPL' for x in client.get('/api/watchlist').json()['items'])

def test_news_endpoint_returns_structured_fallback(monkeypatch):
    import app.main as main
    class FakeResponse:
        text='<rss><channel><item><title>Example headline</title><link>https://example.com/story</link><pubDate>Sat, 14 Nov 2026 10:00:00 GMT</pubDate><description>Summary</description></item></channel></rss>'
        def raise_for_status(self): pass
    class FakeClient:
        def __init__(self,*a,**k): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*a): pass
        async def get(self,url): return FakeResponse()
    monkeypatch.setattr('httpx.AsyncClient',FakeClient)
    r=client.get('/api/news')
    assert r.status_code==200
    assert r.json()['items'][0]['title']=='Example headline'
    assert r.json()['items'][0]['classification']=='publisher_headline_not_independently_verified'

def test_portfolio_and_journal(tmp_path,monkeypatch):
    import app.main as main
    monkeypatch.setattr(main,'DB',tmp_path/'extended.sqlite3')
    # Startup migration is normally run by TestClient context; ensure schema for this isolated DB.
    main.init_extended_db()
    added=client.post('/api/portfolio',json={'symbol':'AAPL','side':'long','quantity':2,'entry_price':100})
    assert added.status_code==200
    assert client.get('/api/portfolio').json()['positions'][0]['symbol']=='AAPL'
    journal=client.post('/api/journal',json={'symbol':'AAPL','note':'Test thesis'})
    assert journal.status_code==200
    assert client.get('/api/journal').json()['entries'][0]['note']=='Test thesis'

def test_backtest_requires_provider(monkeypatch):
    import app.main as main
    async def unavailable(self,symbol): raise main.ProviderUnavailable('No provider key')
    monkeypatch.setattr(main.AlphaVantageProvider,'daily',unavailable)
    r=client.post('/api/backtest/AAPL',json={'fast_period':5,'slow_period':20})
    assert r.status_code==503

def test_report_rejects_non_pdf():
    r=client.post('/api/reports/analyze',files={'file':('bad.txt',b'not a pdf','text/plain')})
    assert r.status_code==415

def test_report_extracts_pdf_and_exports(tmp_path,monkeypatch):
    import app.main as main
    from reportlab.pdfgen import canvas
    from io import BytesIO
    monkeypatch.setattr(main,'DB',tmp_path/'reports.sqlite3')
    main.init_extended_db()
    buf=BytesIO(); c=canvas.Canvas(buf); c.drawString(72,750,'Revenue increased. Net income and cash flow are discussed.'); c.save()
    r=client.post('/api/reports/analyze',files={'file':('annual.pdf',buf.getvalue(),'application/pdf')})
    assert r.status_code==200, r.text
    data=r.json(); assert data['page_count']==1 and data['report_id']>0
    exported=client.get(f"/api/reports/{data['report_id']}/export")
    assert exported.status_code==200 and exported.content.startswith(b'%PDF-')

def test_backtest_chronological_outputs(monkeypatch):
    import app.main as main
    async def fake_daily(self,symbol):
        closes=[100,99,98,97,98,99,101,103,105,107,109,111,113,115,117,119,121,123,125,127,129,131,133,135,137,139,141,143,145,147]
        bars=[{'date':f'2026-01-{i+1:02d}','open':v,'high':v+1,'low':v-1,'close':v,'volume':1000} for i,v in enumerate(closes)]
        return {'symbol':symbol,'candles':bars,'provider':'fixture-for-test','status':'historical'}
    monkeypatch.setattr(main.AlphaVantageProvider,'daily',fake_daily)
    r=client.post('/api/backtest/TEST',json={'fast_period':3,'slow_period':5,'initial_balance':10000,'fee_bps':0,'slippage_bps':0})
    assert r.status_code==200, r.text
    d=r.json(); assert d['bars']==30 and d['equity_curve'][0]['date']=='2026-01-02'
    assert d['final_equity']>=10000 and 'survivorship' in d['limitations']

def test_sec_facts_endpoint_uses_filing_metadata(monkeypatch):
    import app.main as main
    class Resp:
        def __init__(self,payload): self.payload=payload
        def raise_for_status(self): return None
        def json(self): return self.payload
    class FakeClient:
        def __init__(self,*a,**k): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*a): pass
        async def get(self,url):
            if 'company_tickers.json' in url: return Resp({'0':{'ticker':'TEST','cik_str':123,'title':'Test Corp'}})
            return Resp({'entityName':'Test Corp','facts':{'us-gaap':{'Assets':{'units':{'USD':[{'val':1000,'end':'2025-12-31','filed':'2026-02-01','form':'10-K'}]}}}}})
    monkeypatch.setattr('httpx.AsyncClient',FakeClient)
    r=client.get('/api/fundamentals/TEST')
    assert r.status_code==200
    fact=r.json()['facts']['assets']
    assert fact['value']==1000 and fact['period_end']=='2025-12-31' and fact['filed']=='2026-02-01'
