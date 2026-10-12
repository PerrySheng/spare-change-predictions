"""Documented Gemini and Plaid HTTP APIs. No mock fallback lives here."""
import base64,hashlib,hmac,json,os,threading,time
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation
from urllib.parse import quote
import httpx
from .scoring import topic_for

class ProviderError(Exception): pass
class ProviderRejected(ProviderError):
    """A definite rejection before any order was accepted."""
    pass

def http_json(method,url,**kwargs):
    try:
        r=httpx.request(method,url,timeout=25,**kwargs)
        if not r.is_success:
            try:
                body=r.json(); reason=body.get('reason') or body.get('error_code') or body.get('error') or body.get('message') or 'request rejected'
            except ValueError: reason='request rejected'
            error=ProviderRejected if 400<=r.status_code<500 else ProviderError
            raise error(f'Provider returned HTTP {r.status_code}: {reason}')
        return r.json()
    except (httpx.HTTPError,ValueError) as exc:
        raise ProviderError('Provider is unreachable or returned invalid data. Try again.') from exc

class Gemini:
    SANDBOX='https://api.sandbox.gemini.com'
    def __init__(self,base_url=None):
        self.base_url=(base_url or os.getenv('GEMINI_MARKET_URL','https://api.gemini.com')).rstrip('/')
        if self.base_url not in ['https://api.gemini.com',self.SANDBOX]: raise ValueError('Unsupported Gemini host')
        self._cached=None; self._cached_at=0; self._lock=threading.Lock(); self._nonce=0
    def normalize(self,event):
        result=[]
        for c in event.get('contracts',[]):
            for outcome in ['yes','no']:
                prices=c.get('prices') or {}; price=(prices.get('buy') or {}).get(outcome)
                try:
                    if price is not None and not 0<Decimal(price)<1: price=None
                except (InvalidOperation,TypeError): price=None
                result.append({'id':c.get('instrumentSymbol'),'event_ticker':event.get('ticker'),'title':event.get('title',''),'label':c.get('label',''),'category':event.get('category',''),'topic':topic_for(event.get('category','')),'outcome':outcome,'price':price,'sell_price':(prices.get('sell') or {}).get(outcome),'closes_at':c.get('expiryDate') or event.get('expiryDate'),'volume':event.get('volume'),'quantity_minimum':c.get('quantityMinimum'),'quantity_increment':c.get('quantityIncrement'),'price_minimum':c.get('priceMinimum'),'price_increment':c.get('priceIncrement'),'status':c.get('status'),'market_state':c.get('marketState'),'resolution':c.get('resolutionSide'),'terms_url':c.get('termsAndConditionsUrl')})
        for child in event.get('events',[]): result.extend(self.normalize(child))
        return result
    def markets(self):
        with self._lock:
            if self._cached is not None and time.monotonic()-self._cached_at<15: return self._cached
            markets=[]; offset=0
            for _ in range(30):
                data=http_json('GET',self.base_url+'/v1/prediction-markets/events',params={'status':'active','limit':500,'offset':offset})
                if not isinstance(data.get('data'),list): raise ProviderError('Gemini market response has no event list.')
                for event in data['data']: markets.extend(self.normalize(event))
                offset+=len(data['data'])
                if offset>=data.get('pagination',{}).get('total',offset) or not data['data']: break
            else: raise ProviderError('Market pagination exceeded the supported limit.')
            markets=[m for m in markets if m['id'] and m['price'] is not None and m['status']=='active' and m['market_state'] in [None,'open']]
            self._cached=markets; self._cached_at=time.monotonic(); return markets
    def event(self,ticker):
        data=http_json('GET',self.base_url+'/v1/prediction-markets/events/'+quote(ticker,safe=''))
        return self.normalize(data)
    def market(self,symbol,outcome):
        # Discovery is cached, but execution always checks the event again.
        matched=next((m for m in self.markets() if m['id']==symbol and m['outcome']==outcome),None)
        if not matched: raise ProviderError('This contract is no longer in the open market feed.')
        fresh=next((m for m in self.event(matched['event_ticker']) if m['id']==symbol and m['outcome']==outcome),None)
        if not fresh: raise ProviderError('Contract disappeared from the event.')
        return fresh
    def private(self,path,params=None,method='POST'):
        key=os.getenv('GEMINI_API_KEY'); secret=os.getenv('GEMINI_API_SECRET')
        if not key or not secret: raise ProviderError('Set GEMINI_API_KEY and GEMINI_API_SECRET from a Gemini sandbox account in .env.')
        params=dict(params or {})
        if key.startswith('master-') and path.startswith('/v1/prediction-markets/'):
            account=params.get('account') or os.getenv('GEMINI_ACCOUNT','').strip()
            if not isinstance(account,str) or not account.strip():
                raise ProviderRejected('Master Gemini keys require GEMINI_ACCOUNT in .env. Use the account short name returned by /v1/account/list.')
            params['account']=account.strip()
        with self._lock:
            nonce=time.time() if os.getenv('GEMINI_NONCE_MODE','time')=='time' else max(int(time.time()*1000),self._nonce+1)
            self._nonce=nonce
            payload=base64.b64encode(json.dumps({'request':path,'nonce':nonce,**params},separators=(',',':')).encode())
            headers={'Content-Type':'text/plain','Content-Length':'0','Cache-Control':'no-cache','X-GEMINI-APIKEY':key,'X-GEMINI-PAYLOAD':payload.decode(),'X-GEMINI-SIGNATURE':hmac.new(secret.encode(),payload,hashlib.sha384).hexdigest()}
            return http_json(method,self.SANDBOX+path,headers=headers,content=b'')
    def ensure_trading_ready(self):
        if self.base_url!=self.SANDBOX: raise ProviderRejected('Sandbox orders require sandbox market prices. Set GEMINI_MARKET_URL=https://api.sandbox.gemini.com.')
        terms=self.private('/v1/prediction-markets/terms/status',method='GET')
        if not terms.get('hasAcceptedLatest'): raise ProviderRejected('Review and accept the latest Gemini Predictions terms in your sandbox account first.')
    def place_order(self,market,quantity):
        self.ensure_trading_ready()
        return self.private('/v1/prediction-markets/order',{'symbol':market['id'],'orderType':'limit','side':'buy','outcome':market['outcome'],'quantity':str(quantity),'price':str(market['price']),'timeInForce':'fill-or-kill'})
    def lookup_order(self,market_id,order_id):
        for path in ['/v1/prediction-markets/orders/active','/v1/prediction-markets/orders/history']:
            for offset in range(0,10000,100):
                data=self.private(path,{'symbol':market_id,'limit':100,'offset':offset})
                orders=data.get('orders',[])
                found=next((o for o in orders if str(o['orderId'])==str(order_id)),None)
                if found: return found
                if len(orders)<100: break
        raise ProviderError('Order was not found. Reservation remains until its status is verified.')

class Plaid:
    def call(self,path,params=None):
        key=os.getenv('PLAID_CLIENT_ID'); secret=os.getenv('PLAID_SECRET')
        if not key or not secret: raise ProviderError('Set PLAID_CLIENT_ID and PLAID_SECRET in .env to run the Plaid sandbox demo. You can also add a purchase manually.')
        if os.getenv('PLAID_ENV','sandbox')!='sandbox': raise ProviderError('This demo supports PLAID_ENV=sandbox only.')
        return http_json('POST','https://sandbox.plaid.com'+path,json={'client_id':key,'secret':secret,**(params or {})})
    def connect(self,webhook=None):
        options={'override_username':'user_transactions_dynamic','override_password':'pass_good'}
        if webhook: options['webhook']=webhook
        token=self.call('/sandbox/public_token/create',{'institution_id':'ins_109508','initial_products':['transactions'],'options':options})
        return self.call('/item/public_token/exchange',{'public_token':token['public_token']})
    def sync(self,access_token,cursor=''):
        # Restart the full pagination batch after a mutation, per Plaid's sync contract.
        for _ in range(3):
            current=cursor; added=[]; modified=[]; removed=[]
            try:
                for _ in range(100):
                    data=self.call('/transactions/sync',{'access_token':access_token,'cursor':current,'count':500,'options':{'include_original_description':True}})
                    added.extend(data['added']); modified.extend(data['modified']); removed.extend(data['removed']); current=data['next_cursor']
                    if not data['has_more']: return {'added':added,'modified':modified,'removed':removed,'cursor':current}
                raise ProviderError('Plaid sync exceeded the supported page limit.')
            except ProviderError as exc:
                if 'TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION' not in str(exc): raise
        raise ProviderError('Plaid transactions changed during all three sync attempts. Try again.')
    def create_purchases(self,access_token,purchases):
        today=date.today().isoformat()
        return self.call('/sandbox/transactions/create',{'access_token':access_token,'transactions':[{'amount':p['amount'],'description':p.get('description',p['merchant']),'date_posted':today,'date_transacted':today,'iso_currency_code':'USD'} for p in purchases]})
