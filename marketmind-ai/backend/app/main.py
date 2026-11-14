from __future__ import annotations
import os, re, sqlite3, time, json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .indicators import analyze
from .providers import AlphaVantageProvider, TwelveDataProvider, ProviderUnavailable

ROOT=Path(__file__).resolve().parents[2]
DB=Path(os.getenv("MARKETMIND_DB",ROOT/"marketmind.sqlite3"))
app=FastAPI(title="MarketMind AI API",version="0.2.0",description="Local-first financial research, quantitative testing and education")
cors_origins=[x.strip() for x in os.getenv("CORS_ORIGINS","http://localhost:8000,http://127.0.0.1:8000,capacitor://localhost,http://localhost,https://localhost").split(",") if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=cors_origins,allow_credentials=False,allow_methods=["GET","POST","DELETE"],allow_headers=["Content-Type"])

class WatchlistItem(BaseModel): symbol:str=Field(min_length=1,max_length=24)
class ForexRisk(BaseModel): balance:float=Field(gt=0); risk_percent:float=Field(gt=0,le=100); entry:float=Field(gt=0); stop:float=Field(gt=0); pip_size:float=Field(gt=0); pip_value_per_lot:float=Field(gt=0); spread_pips:float=Field(ge=0); commission_per_lot:float=Field(ge=0)

def db():
    con = sqlite3.connect(DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS watchlist(
            symbol TEXT PRIMARY KEY,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS market_cache(
            symbol TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            cached_at REAL NOT NULL
        )
    """)
    con.commit()
    return con
async def get_daily_history(symbol: str):
    symbol = symbol.upper()
    con = db()

    row = con.execute(
        "SELECT payload, cached_at FROM market_cache WHERE symbol=?",
        (symbol,)
    ).fetchone()

    con.close()

    now = time.time()

    # Reuse successful data for 24 hours.
    if row and now - row[1] < 86400:
        data = json.loads(row[0])
        data["cache_status"] = "cached"
        return data

    # Fetch new data when the cache expires.
    try:
        data = await AlphaVantageProvider().daily(symbol)

    except ProviderUnavailable:
        # If the provider is unavailable, use older saved data
        # rather than making the app completely unusable.
        if row:
            data = json.loads(row[0])
            data["cache_status"] = "stale_fallback"
            data["cache_age_hours"] = round(
                (now - row[1]) / 3600, 1
            )
            return data

        raise

    # Save only successful provider responses.
    con = db()
    con.execute(
        """
        INSERT OR REPLACE INTO market_cache
        (symbol, payload, cached_at)
        VALUES (?, ?, ?)
        """,
        (symbol, json.dumps(data), now)
    )
    con.commit()
    con.close()

    data["cache_status"] = "provider"
    return data    

@app.get("/api/health")
def health(): return {"status":"ok","app":"MarketMind AI","market_data_configured":bool(os.getenv("ALPHA_VANTAGE_API_KEY")),"data_mode":"provider_required_for_real_quotes"}

@app.get("/api/search")
def search(q:str):
    q=q.strip().upper()
    if not q or len(q)>24 or not re.fullmatch(r"[A-Z0-9.^=_-]+",q): raise HTTPException(400,"Enter a valid symbol or pair using letters, numbers, dots, hyphens, or carets.")
    known={"AAPL":"Apple Inc. (provider symbol search not yet enabled)","MSFT":"Microsoft Corporation","NVDA":"NVIDIA Corporation","AMZN":"Amazon.com, Inc.","GOOGL":"Alphabet Inc.","EURUSD":"EUR/USD forex pair (provider mapping may differ)","USDZAR":"USD/ZAR forex pair (provider mapping may differ)"}
    return {"query":q,"matches":[{"symbol":q,"description":known.get(q,"Symbol accepted for provider lookup; instrument identity must be confirmed by provider.")}],"source":"Local symbol helper; not an exchange master list"}

@app.get("/api/market/{symbol}")
async def market(symbol:str):
    if not re.fullmatch(r"[A-Za-z0-9.^=_-]{1,24}",symbol): raise HTTPException(400,"Invalid symbol")
    try: data=await get_daily_history(symbol.upper())
    except ProviderUnavailable as e: raise HTTPException(503,detail={"status":"unavailable","message":str(e),"data_status":"unavailable"})
    data["analysis"]=analyze([x["close"] for x in data["candles"]],[x["high"] for x in data["candles"]],[x["low"] for x in data["candles"]])
    data["last_close"]=data["candles"][-1]["close"] if data["candles"] else None
    return data

@app.get("/api/watchlist")
def get_watchlist():
    con=db(); rows=con.execute("SELECT symbol,added_at FROM watchlist ORDER BY added_at DESC").fetchall(); con.close(); return {"items":[{"symbol":r[0],"added_at":r[1]} for r in rows]}

@app.post("/api/watchlist")
def add_watchlist(item:WatchlistItem):
    symbol=item.symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9.^=_-]{1,24}",symbol): raise HTTPException(400,"Invalid symbol")
    con=db(); con.execute("INSERT OR IGNORE INTO watchlist(symbol) VALUES(?)",(symbol,)); con.commit(); con.close(); return {"symbol":symbol,"saved":True}

@app.delete("/api/watchlist/{symbol}")
def remove_watchlist(symbol:str):
    con=db(); con.execute("DELETE FROM watchlist WHERE symbol=?",(symbol.upper(),)); con.commit(); con.close(); return {"symbol":symbol.upper(),"removed":True}

@app.post("/api/forex/position-size")
def forex_size(x:ForexRisk):
    distance=abs(x.entry-x.stop)
    if distance<=0: raise HTTPException(400,"Entry and stop must differ")
    pips=distance/x.pip_size
    risk_cash=x.balance*x.risk_percent/100
    cost_per_lot=(pips+x.spread_pips)*x.pip_value_per_lot+x.commission_per_lot
    if cost_per_lot<=0: raise HTTPException(400,"Calculated per-lot risk must be positive")
    lots=risk_cash/cost_per_lot
    return {"stop_distance_pips":pips,"risk_budget":risk_cash,"estimated_loss_at_stop":lots*cost_per_lot,"position_size_lots":lots,"estimated_cost_per_lot":cost_per_lot,"warning":"Illustrative calculator only. Pip value depends on pair, account currency, broker contract size and conversion rates. Slippage, gaps and leverage can increase losses."}

@app.get("/api/education")
def education():
    return {"topics":[{"term":"RSI","simple":"The Relative Strength Index compares recent upward and downward price changes on a 0–100 scale.","advanced":"Wilder-smoothed relative strength: RSI = 100 − 100/(1 + RS), where RS is smoothed average gain divided by smoothed average loss.","use":"Some traders watch values above 70 or below 30 as possible stretched conditions, not automatic reversal signals.","limitation":"RSI can remain elevated or depressed in strong trends."},{"term":"Moving average","simple":"An average price over a chosen number of periods that smooths short-term noise.","advanced":"SMA is the arithmetic mean of the last n observations; EMA weights recent observations more heavily with alpha = 2/(n+1).","use":"Trend context and dynamic reference levels.","limitation":"Moving averages lag and can whipsaw in sideways markets."},{"term":"ATR","simple":"Average True Range estimates how much an instrument moves, not which direction it moves.","advanced":"Wilder ATR smooths true range, which includes gaps relative to the prior close.","use":"Volatility context and position-risk planning.","limitation":"ATR is not a directional forecast and can expand sharply around events."}]}

@app.get("/")
def index(): return FileResponse(ROOT/"frontend"/"index.html")


# Phase 2–4 research services. These use deterministic calculations and public sources.
import json, math, tempfile, xml.etree.ElementTree as ET
from datetime import date
from fastapi import UploadFile, File
from fastapi.responses import StreamingResponse
from io import BytesIO

@app.on_event("startup")
def init_extended_db():
    con=db()
    con.executescript('''
    CREATE TABLE IF NOT EXISTS virtual_positions(id INTEGER PRIMARY KEY AUTOINCREMENT,symbol TEXT NOT NULL,side TEXT NOT NULL CHECK(side IN ('long','short')),quantity REAL NOT NULL CHECK(quantity>0),entry_price REAL NOT NULL CHECK(entry_price>0),created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS journal(id INTEGER PRIMARY KEY AUTOINCREMENT,symbol TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS saved_reports(id INTEGER PRIMARY KEY AUTOINCREMENT,filename TEXT NOT NULL,report_json TEXT NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    ''')
    con.close()

class PortfolioPosition(BaseModel):
    symbol:str=Field(min_length=1,max_length=24)
    side:str=Field(pattern='^(long|short)$')
    quantity:float=Field(gt=0,le=1e12)
    entry_price:float=Field(gt=0,le=1e15)

class JournalEntry(BaseModel):
    symbol:str=Field(min_length=1,max_length=24)
    note:str=Field(min_length=1,max_length=5000)

class BacktestRequest(BaseModel):
    fast_period:int=Field(default=20,ge=2,le=200)
    slow_period:int=Field(default=50,ge=3,le=500)
    initial_balance:float=Field(default=10000,gt=0,le=1e12)
    fee_bps:float=Field(default=5,ge=0,le=500)
    slippage_bps:float=Field(default=2,ge=0,le=500)

@app.get('/api/news')
async def news(limit:int=20):
    """Fetch headline metadata from a small allowlist of public RSS feeds; no AI or rumor verdicts."""
    import httpx
    feeds=[('Reuters Business','https://feeds.reuters.com/reuters/businessNews'),('MarketWatch Top Stories','https://feeds.marketwatch.com/marketwatch/topstories/'),('CNBC Finance','https://www.cnbc.com/id/10000664/device/rss/rss.html')]
    items=[]; errors=[]
    async with httpx.AsyncClient(timeout=12,headers={'User-Agent':'MarketMindAI/0.2 (personal research app)'}) as client:
        for publisher,url in feeds:
            try:
                res=await client.get(url); res.raise_for_status(); root=ET.fromstring(res.text)
                for node in root.findall('.//item'):
                    title=(node.findtext('title') or '').strip(); link=(node.findtext('link') or '').strip(); published=(node.findtext('pubDate') or '').strip(); summary=(node.findtext('description') or '').strip()
                    if title and link.startswith('https://'):
                        items.append({'title':title,'publisher':publisher,'url':link,'published_at':published or None,'summary':re.sub('<[^>]+>',' ',summary)[:500], 'classification':'publisher_headline_not_independently_verified'})
            except Exception as exc: errors.append({'publisher':publisher,'error':type(exc).__name__})
    # Stable deduplication; preserve feed order.
    seen=set(); unique=[]
    for x in items:
        if x['url'] not in seen: seen.add(x['url']); unique.append(x)
    return {'items':unique[:max(1,min(limit,50))],'sources_checked':len(feeds),'errors':errors,'status':'available' if unique else 'unavailable','disclaimer':'Headlines and publisher summaries are not independently verified. No rumor is classified as confirmed by repetition.'}

@app.get('/api/fundamentals/{ticker}')
async def fundamentals(ticker:str):
    """Retrieve US issuer facts from SEC companyfacts when ticker mapping is available."""
    ticker=ticker.upper()
    if not re.fullmatch(r'[A-Z0-9.-]{1,12}',ticker): raise HTTPException(400,'Invalid ticker')
    import httpx
    headers={'User-Agent':os.getenv('SEC_USER_AGENT','MarketMindAI research contact@example.com'),'Accept-Encoding':'gzip, deflate'}
    try:
        async with httpx.AsyncClient(timeout=20,headers=headers) as client:
            mapping_response=await client.get('https://www.sec.gov/files/company_tickers.json'); mapping_response.raise_for_status()
            companies=mapping_response.json(); match=next((v for v in companies.values() if v.get('ticker','').upper()==ticker),None)
            if not match: raise HTTPException(404,'Ticker not found in SEC company ticker mapping; this endpoint covers SEC filers, not all global issuers.')
            cik=str(match['cik_str']).zfill(10)
            facts_res=await client.get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json'); facts_res.raise_for_status(); payload=facts_res.json()
    except HTTPException: raise
    except Exception as exc: raise HTTPException(503,f'SEC data unavailable ({type(exc).__name__}); retry later.')
    us=payload.get('facts',{}).get('us-gaap',{})
    def latest(tag):
        entry=us.get(tag)
        if not entry:return None
        units=entry.get('units',{}); rows=next(iter(units.values()),[])
        rows=sorted((r for r in rows if r.get('form') in ('10-K','10-Q') and r.get('filed')),key=lambda r:r['filed'],reverse=True)
        return ({'value':rows[0].get('val'),'unit':next(iter(units.keys()),None),'period_end':rows[0].get('end'),'filed':rows[0].get('filed'),'form':rows[0].get('form')} if rows else None)
    selected={k:latest(v) for k,v in {'revenue':'RevenueFromContractWithCustomerExcludingAssessedTax','net_income':'NetIncomeLoss','operating_cash_flow':'NetCashProvidedByUsedInOperatingActivities','assets':'Assets','liabilities':'Liabilities','stockholders_equity':'StockholdersEquity','eps_diluted':'EarningsPerShareDiluted'}.items()}
    return {'ticker':ticker,'company':payload.get('entityName'),'cik':cik,'source':'SEC EDGAR Company Facts','retrieved_at_utc':date.today().isoformat(),'facts':selected,'limitations':'US SEC filers only. Latest facts can represent different reporting periods and units; compare period_end, filed, form and unit before calculating ratios. Missing facts are null.'}

@app.post('/api/backtest/{symbol}')
async def backtest(symbol:str, cfg:BacktestRequest):
    if cfg.fast_period>=cfg.slow_period: raise HTTPException(400,'fast_period must be less than slow_period')
    try: d=await get_daily_history(symbol.upper())
    except ProviderUnavailable as exc: raise HTTPException(503,detail={'status':'unavailable','message':str(exc)})
    bars=d['candles']; closes=[float(x['close']) for x in bars]
    if len(closes)<cfg.slow_period+2: raise HTTPException(422,'Insufficient daily history for requested moving-average periods.')
    # Signal calculated at close t; position applies to next close-to-close return.
    cash=cfg.initial_balance; units=0.0; equity=[]; trades=[]; trade_results=[]; position=0; entry_cost=0.0
    fee=(cfg.fee_bps+cfg.slippage_bps)/10000
    for i in range(1,len(closes)):
        hist=closes[:i]
        f=sum(hist[-cfg.fast_period:])/cfg.fast_period if len(hist)>=cfg.fast_period else None
        s=sum(hist[-cfg.slow_period:])/cfg.slow_period if len(hist)>=cfg.slow_period else None
        desired=1 if f is not None and s is not None and f>s else 0
        px=closes[i]
        if desired!=position and f is not None and s is not None:
            if desired==1:
                units=cash/(px*(1+fee)); entry_cost=units*px*(1+fee); cash-=entry_cost; trades.append({'date':bars[i]['date'],'side':'buy','price':px})
            else:
                proceeds=units*px*(1-fee); pnl=proceeds-entry_cost; trade_results.append(pnl); cash+=proceeds; units=0; entry_cost=0.0; trades.append({'date':bars[i]['date'],'side':'sell','price':px,'net_pnl':pnl})
            position=desired
        equity.append({'date':bars[i]['date'],'equity':cash+units*px})
    final=equity[-1]['equity']; peak=cfg.initial_balance; maxdd=0.0
    for row in equity:
        peak=max(peak,row['equity']); maxdd=min(maxdd,row['equity']/peak-1)
    returns=[equity[i]['equity']/equity[i-1]['equity']-1 for i in range(1,len(equity)) if equity[i-1]['equity']>0]
    sharpe=(sum(returns)/len(returns))/(math.sqrt(sum((x-sum(returns)/len(returns))**2 for x in returns)/(len(returns)-1))*math.sqrt(252)) if len(returns)>1 and sum((x-sum(returns)/len(returns))**2 for x in returns)>0 else None
    closed=len(trade_results); wins=[x for x in trade_results if x>0]; losses=[x for x in trade_results if x<0]; gross_profit=sum(wins); gross_loss=abs(sum(losses)); span_days=(date.fromisoformat(bars[-1]['date'])-date.fromisoformat(bars[0]['date'])).days
    annualized=((final/cfg.initial_balance)**(365.25/span_days)-1)*100 if span_days>365 and final>0 else None
    return {'symbol':symbol.upper(),'strategy':f'SMA {cfg.fast_period}/{cfg.slow_period} long/cash','data_status':d['status'],'provider':d['provider'],'first_date':bars[0]['date'],'last_date':bars[-1]['date'],'bars':len(bars),'initial_balance':cfg.initial_balance,'final_equity':final,'total_return_pct':(final/cfg.initial_balance-1)*100,'annualized_return_pct':annualized,'max_drawdown_pct':maxdd*100,'sharpe_daily_annualized':sharpe,'closed_trades':closed,'win_rate_pct':(len(wins)/closed*100 if closed else None),'profit_factor':(gross_profit/gross_loss if gross_loss>0 else (None if gross_profit==0 else 'no_losses_in_sample')),'average_winning_trade_pnl':(sum(wins)/len(wins) if wins else None),'average_losing_trade_pnl':(sum(losses)/len(losses) if losses else None),'trade_events':trades,'equity_curve':equity,'cost_assumption_bps_each_turnover':cfg.fee_bps+cfg.slippage_bps,'limitations':'Illustrative daily close model. Signal is applied after its calculation bar. Long-only, fractional units, no dividends, taxes, borrow, market impact, spread beyond configured bps, delisted assets or survivorship-bias correction. No out-of-sample guarantee.'}

@app.get('/api/portfolio')
def portfolio():
    con=db(); rows=con.execute('SELECT id,symbol,side,quantity,entry_price,created_at FROM virtual_positions ORDER BY id DESC').fetchall(); con.close()
    return {'positions':[{'id':r[0],'symbol':r[1],'side':r[2],'quantity':r[3],'entry_price':r[4],'created_at':r[5]} for r in rows],'mode':'virtual_only_no_broker_execution'}

@app.post('/api/portfolio')
def portfolio_add(x:PortfolioPosition):
    con=db(); cur=con.execute('INSERT INTO virtual_positions(symbol,side,quantity,entry_price) VALUES(?,?,?,?)',(x.symbol.upper(),x.side,x.quantity,x.entry_price)); con.commit(); ident=cur.lastrowid; con.close(); return {'id':ident,'saved':True,'mode':'virtual_only'}

@app.delete('/api/portfolio/{position_id}')
def portfolio_delete(position_id:int):
    con=db(); cur=con.execute('DELETE FROM virtual_positions WHERE id=?',(position_id,)); con.commit(); con.close()
    if not cur.rowcount: raise HTTPException(404,'Position not found')
    return {'deleted':True,'id':position_id}

@app.get('/api/journal')
def journal_list():
    con=db(); rows=con.execute('SELECT id,symbol,note,created_at FROM journal ORDER BY id DESC LIMIT 200').fetchall(); con.close(); return {'entries':[{'id':r[0],'symbol':r[1],'note':r[2],'created_at':r[3]} for r in rows]}

@app.post('/api/journal')
def journal_add(x:JournalEntry):
    con=db(); cur=con.execute('INSERT INTO journal(symbol,note) VALUES(?,?)',(x.symbol.upper(),x.note)); con.commit(); ident=cur.lastrowid; con.close(); return {'id':ident,'saved':True}

@app.post('/api/reports/analyze')
async def report_analyze(file:UploadFile=File(...)):
    if not file.filename or not file.filename.lower().endswith('.pdf') or file.content_type not in ('application/pdf','application/octet-stream'):
        raise HTTPException(415,'Upload a PDF file only.')
    raw=await file.read(8*1024*1024+1)
    if len(raw)>8*1024*1024: raise HTTPException(413,'PDF exceeds the 8 MB upload limit.')
    if not raw.startswith(b'%PDF-'): raise HTTPException(415,'File content is not a valid PDF header.')
    try:
        from pypdf import PdfReader
        reader=PdfReader(BytesIO(raw),strict=True)
        if reader.is_encrypted: raise HTTPException(422,'Encrypted PDFs are not supported.')
        pages=[]
        for i,p in enumerate(reader.pages[:100]):
            text=(p.extract_text() or '')[:30000]
            pages.append({'page':i+1,'text':text})
    except HTTPException: raise
    except Exception as exc: raise HTTPException(422,f'PDF could not be safely parsed ({type(exc).__name__}).')
    combined='\n'.join(p['text'] for p in pages)
    if not combined.strip(): raise HTTPException(422,'No extractable text found. Scanned PDFs require OCR, which is not enabled.')
    terms=['revenue','net income','cash flow','total assets','total liabilities','debt','risk factors','guidance','going concern','impairment']
    found={term:[p['page'] for p in pages if term in p['text'].lower()] for term in terms}
    found={k:v for k,v in found.items() if v}
    report={'filename':Path(file.filename).name[:180],'page_count':len(pages),'extracted_characters':len(combined),'executive_summary':'Text extraction completed. This is not an AI investment opinion or a complete financial-statement interpretation. Review cited pages and extracted values manually.','topic_page_references':found,'pages':pages,'limitations':['PDF text extraction only; no OCR for scanned pages.','Tables and multi-column layouts may be extracted incorrectly.','No financial values are invented or automatically reconciled.','No file is sent to an external AI provider.']}
    con=db(); cur=con.execute('INSERT INTO saved_reports(filename,report_json) VALUES(?,?)',(report['filename'],json.dumps(report))); con.commit(); report['report_id']=cur.lastrowid; con.close()
    return report

@app.get('/api/reports/{report_id}/export')
def report_export(report_id:int):
    con=db(); row=con.execute('SELECT filename,report_json FROM saved_reports WHERE id=?',(report_id,)).fetchone(); con.close()
    if not row: raise HTTPException(404,'Report not found')
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        data=json.loads(row[1]); buff=BytesIO(); doc=SimpleDocTemplate(buff,pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=18*mm,bottomMargin=18*mm); styles=getSampleStyleSheet(); story=[Paragraph('MarketMind AI — Document Extraction Report',styles['Title']),Paragraph(row[0].replace('&','&amp;'),styles['Heading2']),Paragraph(data['executive_summary'],styles['BodyText']),Spacer(1,10)]
        for term,pages in data['topic_page_references'].items(): story.append(Paragraph(f'{term.title()}: page(s) {", ".join(map(str,pages))}',styles['BodyText']))
        story.append(Spacer(1,12)); story.append(Paragraph('Limitations',styles['Heading2']))
        for item in data['limitations']: story.append(Paragraph('• '+item,styles['BodyText']))
        for page in data['pages']:
            if page['text'].strip():
                story.extend([PageBreak(),Paragraph(f'Extracted text — page {page["page"]}',styles['Heading2']),Paragraph(page['text'][:12000].replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('\n','<br/>'),styles['Code'])])
        doc.build(story); buff.seek(0)
        return StreamingResponse(buff,media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="marketmind-report-{report_id}.pdf"'})
    except Exception as exc: raise HTTPException(500,f'PDF export failed ({type(exc).__name__}).')

@app.get('/api/reports')
def report_list():
    con=db(); rows=con.execute('SELECT id,filename,created_at FROM saved_reports ORDER BY id DESC').fetchall(); con.close(); return {'reports':[{'id':r[0],'filename':r[1],'created_at':r[2]} for r in rows]}


# Keep the static frontend mount last so all API routes remain reachable.
app.mount("/",StaticFiles(directory=ROOT/"frontend",html=True),name="frontend")
