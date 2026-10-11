"""Private friend-test access and server-verified profile cookies in production."""
import hashlib,hmac,os,time
from collections import defaultdict,deque
from threading import Lock
from urllib.parse import parse_qs,urlsplit
from fastapi import Request
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse

ACCESS_COOKIE='spare-access'
PROFILE_COOKIE='spare-profile'
PRIVATE=('/users/','/squads','/roundups','/purchases','/transactions','/dashboard','/suggestions','/swarm/run','/xrpl','/news','/markets/quote','/markets/context','/demo','/plaid')

class FriendAccess:
    def __init__(self):
        self.enabled=os.getenv('APP_ENV','development')=='production'
        self.secret=os.getenv('APP_SESSION_SECRET','')
        self.code=os.getenv('DEMO_ACCESS_CODE','')
        self.attempts=defaultdict(deque);self.lock=Lock()
        if self.enabled and (len(self.secret)<32 or len(self.code)<12):
            raise ValueError('Production requires APP_SESSION_SECRET (32+ characters) and DEMO_ACCESS_CODE (12+ characters).')
    def sign(self,value):
        return value+'.'+hmac.new(self.secret.encode(),value.encode(),hashlib.sha256).hexdigest()
    def read(self,value,prefix):
        if not value:return None
        payload,separator,signature=value.rpartition('.')
        if not separator or not payload.startswith(prefix) or not hmac.compare_digest(self.sign(payload),value):return None
        return payload[len(prefix):]
    def set_profile(self,response,user_id):
        if self.enabled:response.set_cookie(PROFILE_COOKIE,self.sign('profile:'+user_id),httponly=True,secure=True,samesite='lax',max_age=30*86400,path='/')
    def allow_attempt(self,address):
        with self.lock:
            now=time.monotonic();history=self.attempts[address]
            while history and history[0]<now-300:history.popleft()
            if len(history)>=10:return False
            history.append(now)
            if len(self.attempts)>2000:
                self.attempts=defaultdict(deque,{k:v for k,v in self.attempts.items() if v and v[-1]>=now-300})
            return True

def register_access(app):
    access=FriendAccess();app.state.access=access
    @app.get('/access',include_in_schema=False)
    def access_page():
        if not access.enabled:return RedirectResponse('/')
        return HTMLResponse('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>spare · Friend test</title><style>body{margin:0;font:16px system-ui;background:#edf2fc;color:#162344;display:grid;place-items:center;min-height:100dvh}main{background:white;padding:32px;border-radius:20px;width:min(330px,80vw)}h1{font-size:30px}p{line-height:1.6;color:#65779a}input,button{box-sizing:border-box;width:100%;padding:14px;margin-top:12px;border-radius:10px;border:1px solid #dbe3f2;font:inherit}button{background:#2453e8;color:white;cursor:pointer}label{display:block;margin-top:24px}</style><main><h1>spare.</h1><p>A little change, together.<br>Enter the friend test access code.</p><form method="post" action="/access"><label for="code">Access code</label><input id="code" name="code" type="password" autocomplete="current-password" required maxlength="100"><button>Open the app</button></form></main></html>''')
    @app.post('/access',include_in_schema=False)
    async def enter(request:Request):
        if not access.enabled:return RedirectResponse('/',status_code=303)
        if not access.allow_attempt(request.client.host if request.client else 'unknown'):
            return JSONResponse(status_code=429,content={'detail':'Too many attempts. Try again in five minutes.'})
        body=await request.body()
        if len(body)>1000:return JSONResponse(status_code=400,content={'detail':'Enter the access code.'})
        code=parse_qs(body.decode('utf-8',errors='replace')).get('code',[''])[0]
        if not hmac.compare_digest(code.encode(),access.code.encode()):return JSONResponse(status_code=401,content={'detail':'Access code did not match. Go back and try again.'})
        response=RedirectResponse('/',status_code=303)
        response.set_cookie(ACCESS_COOKIE,access.sign('access:friends'),httponly=True,secure=True,samesite='lax',max_age=30*86400,path='/')
        return response
    @app.middleware('http')
    async def protect(request,call_next):
        if not access.enabled:return await call_next(request)
        path=request.url.path
        if path=='/health' or path.startswith('/webhooks/'):
            return await call_next(request)
        origin=request.headers.get('origin')
        if request.method not in ('GET','HEAD','OPTIONS') and origin and urlsplit(origin).netloc!=request.url.netloc:
            return JSONResponse(status_code=403,content={'detail':'Use this app from its own website.'})
        if path=='/access':return await call_next(request)
        if access.read(request.cookies.get(ACCESS_COOKIE),'access:')!='friends':
            if request.method=='GET' and 'text/html' in request.headers.get('accept',''):return RedirectResponse('/access',status_code=303)
            return JSONResponse(status_code=401,content={'detail':'Open the app and enter the friend test access code.'})
        if path=='/users' and request.method=='POST':return await call_next(request)
        if path.startswith(PRIVATE):
            user_id=access.read(request.cookies.get(PROFILE_COOKIE),'profile:')
            if not user_id:return JSONResponse(status_code=401,content={'detail':'Complete onboarding in this browser first.'})
            supplied=request.query_params.get('user_id')
            if request.method in ('POST','PATCH','PUT','DELETE'):
                try:
                    payload=await request.json()
                    supplied=payload.get('user_id',supplied) if isinstance(payload,dict) else supplied
                except (ValueError,UnicodeError):pass
            if (supplied is not None and supplied!=user_id) or (path.startswith('/users/') and path.split('/')[2]!=user_id):
                return JSONResponse(status_code=404,content={'detail':'This profile is not yours.'})
        return await call_next(request)
    return access
