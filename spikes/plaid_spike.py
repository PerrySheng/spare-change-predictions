"""Create a dynamic sandbox Item and a custom purchase; never print tokens."""
import json,sys,time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.providers import Plaid,ProviderError

def main():
    try:
        plaid=Plaid(); item=plaid.connect(); token=item['access_token']; cursor=plaid.sync(token)['cursor']
        plaid.create_purchases(token,[{'amount':4.63,'merchant':'Starbucks'}])
        for _ in range(15):
            data=plaid.sync(token,cursor); cursor=data['cursor']
            matches=[t for t in data['added'] if t.get('amount')==4.63 and 'starbucks' in (t.get('name','')+' '+(t.get('merchant_name') or '')).lower()]
            if matches:
                print(json.dumps([{k:t.get(k) for k in ['transaction_id','amount','name','merchant_name','personal_finance_category','pending']} for t in matches],indent=2));return 0
            time.sleep(1)
        print('Purchase created. Plaid has not returned it yet; run /plaid/sync later. No substitute transaction was generated.');return 2
    except ProviderError as exc: print(str(exc));return 1
if __name__=='__main__':sys.exit(main())
