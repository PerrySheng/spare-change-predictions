"""Run from the repository root: .venv/bin/python spikes/gemini_spike.py."""
import json,sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.providers import Gemini,ProviderError

def main():
    try:
        production=Gemini('https://api.gemini.com'); markets=production.markets()
        print(json.dumps({'public_market_feed':'worked','open_outcome_quotes':len(markets),'sample':[{k:m[k] for k in ['id','title','label','category','outcome','price','closes_at','volume']} for m in markets[:10]]},indent=2))
    except ProviderError as exc: print(json.dumps({'public_market_feed':'failed','reason':str(exc)})); return 1
    sandbox=Gemini(Gemini.SANDBOX)
    try:
        sandbox_markets=sandbox.markets(); print(json.dumps({'sandbox_market_feed':'worked','open_outcome_quotes':len(sandbox_markets)}))
        market=next((m for m in sandbox_markets if m['price'] and float(m['quantity_minimum'] or 1)<=1),None)
        if not market: raise ProviderError('No sandbox contract supports one whole contract right now.')
        response=sandbox.place_order(market,1)
        print(json.dumps({'sandbox_order':'submitted','response':response},indent=2))
        print('Submission is not a fill. Inspect status and filledQuantity above. FOK cancels if a full immediate fill is unavailable.')
    except ProviderError as exc:
        print(json.dumps({'sandbox_order':'not_verified','reason':str(exc),'fallback':'TRADING_MODE=paper'},indent=2)); return 2
    return 0
if __name__=='__main__': sys.exit(main())
