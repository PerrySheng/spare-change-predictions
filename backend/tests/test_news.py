from app.news import history_weights, order_markets, related_markets

def market(id,topic):
    return {'id':id,'category':topic,'title':id,'outcome':'yes','price':'0.4','status':'active','closes_at':'2099-01-01T00:00:00Z'}

def test_real_history_changes_feed_for_two_users():
    markets=[market('game','sports'),market('coin','crypto')]
    sports=history_weights([], [{'category':'sports','status':'won','entry_price':'0.4'}]*3)
    crypto=history_weights([], [{'category':'crypto','status':'won','entry_price':'0.5'}]*4)
    assert order_markets(markets,sports)[0]['id']=='game'
    assert order_markets(markets,crypto)[0]['id']=='coin'
    assert sports['sports']['resolved']==3
    assert sports['sports']['edge_score']==0.6

def test_losses_do_not_add_an_edge_boost_and_voids_are_excluded():
    win=history_weights([], [{'category':'sports','status':'won','entry_price':'0.5'}])
    loss=history_weights([], [{'category':'sports','status':'lost','entry_price':'0.5'}])
    void=history_weights([], [{'category':'sports','status':'void','entry_price':'0.5'}])
    assert loss['sports']['weight']<=win['sports']['weight']
    assert loss['sports']['weight']==void['sports']['weight']==1
    assert void['sports']['resolved']==0

def test_related_are_actual_topic_matched_distinct_instruments():
    rows=[market('a','sports'),{**market('a','sports'),'outcome':'no','price':'0.6'},market('b','crypto'),market('c','sports')]
    result=related_markets(rows,rows[0])
    assert [m['id'] for m in result]==['a','c']
    assert result[0]['prices']=={'yes':'0.4','no':'0.6'}

from fastapi.testclient import TestClient
from app.main import create_app
from sqlalchemy.orm import Session
from app.database import Position,Purchase,Roundup
from app.swarm import cache_sources


def test_topic_aliases_and_markets_after_the_first_forty_are_available(tmp_path):
    class BroadFeed(Feed):
        def markets(self):return [market(f'sports-{i}','sports') for i in range(45)]+[market('election','Political'),market('storm','Climate')]
    app=create_app('sqlite:///'+str(tmp_path/'broad.db'),feed=BroadFeed())
    with TestClient(app) as c:
        u=c.post('/users',json={'name':'Reader','interests':['sports']}).json()['id']
        data=c.get('/news/markets',params={'user_id':u}).json()
        assert any(m['id']=='election' and m['topic']=='politics' for m in data['markets'])
        assert any(m['id']=='storm' and m['topic']=='weather' for m in data['markets'])
        assert data['topic_counts']['politics']==1 and data['topic_counts']['weather']==1


def test_topic_reading_returns_real_context_sources_even_without_related_markets(tmp_path):
    app=create_app('sqlite:///'+str(tmp_path/'topics.db'),feed=Feed())
    with TestClient(app) as c:
        u=c.post('/users',json={'name':'Weather reader','interests':[]}).json()['id']
        cache_sources(app.state.engine,'topic:weather',[{'url':'https://weather.example/news','title':'Observed weather news','snippet':'Brief source summary'}],'Context.dev')
        response=c.get('/news/topics/articles',params={'user_id':u,'topic':'weather'})
        assert response.status_code==200,response.text
        assert response.json()['sources'][0]['title']=='Observed weather news'
        assert response.json()['related_markets']==[] and response.json()['cached'] is True
        assert c.get('/news/topics/articles',params={'user_id':u,'topic':'nonsense'}).status_code==422

class Feed:
    def markets(self):
        rows=[market('game','sports'),market('coin','crypto')]
        return rows+[{**r,'outcome':'no','price':'0.6'} for r in rows]
    def market(self,id,outcome):return next(m for m in self.markets() if m['id']==id and m['outcome']==outcome)
    def event(self,ticker):return []


def test_feed_uses_persisted_positions_and_reuses_news_scout_cache(tmp_path):
    app=create_app('sqlite:///'+str(tmp_path/'news.db'),feed=Feed())
    with TestClient(app) as c:
        users=[c.post('/users',json={'name':n,'interests':[],'weekly_cap_cents':500}).json()['id'] for n in ['Sports reader','Crypto reader']]
        with Session(app.state.engine) as s:
            for u,category in zip(users,['sports','crypto']):
                p=Purchase(user_id=u,amount_cents=450,merchant='History',source='manual');s.add(p);s.flush()
                r=Roundup(purchase_id=p.id,amount_cents=50,allocation='market');s.add(r);s.flush()
                s.add(Position(user_id=u,roundup_id=r.id,market_id=category,event_ticker=category,title=category,category=category,outcome='yes',quantity=1,entry_price='0.4',cost_cents=40,fee_cents=2,mode='paper',status='won'))
            s.commit()
        first=[c.get('/news/markets',params={'user_id':u}).json()['markets'][0]['id'] for u in users]
        assert first==['game','coin']
        cache_sources(app.state.engine,'game',[{'title':'Observed source','url':'https://example.org/report','snippet':'Brief public summary'}],'Claude News Scout')
        # register_news closes over its original adapter: missing Context key would
        # fail unless the durable shared cache is actually being reused.
        result=c.get('/news/articles',params={'user_id':users[0],'market_id':'game'})
        assert result.status_code==200,result.text
        assert result.json()['cached'] is True
        assert result.json()['sources'][0]['url']=='https://example.org/report'
        assert [m['id'] for m in result.json()['related_markets']]==['game']
        assert c.get('/news/articles',params={'user_id':'missing','market_id':'game'}).status_code==404


def test_reading_quote_respects_user_budget_pause_and_side(tmp_path):
    app=create_app('sqlite:///'+str(tmp_path/'quote.db'),feed=Feed())
    with TestClient(app) as c:
        u=c.post('/users',json={'name':'Reader','interests':[],'weekly_cap_cents':100}).json()['id']
        p=c.post('/purchases',json={'user_id':u,'amount':'4.01','merchant':'Bookshop'}).json()
        params={'user_id':u,'roundup_id':p['roundup_id'],'market_id':'game','outcome':'no'}
        q=c.get('/markets/quote',params=params)
        assert q.status_code==200,q.text
        assert q.json()['market']['outcome']=='no' and q.json()['market']['price']=='0.6'
        assert q.json()['quote']['total_cents']<=99
        c.patch('/users/'+u,json={'paused':True})
        assert c.get('/markets/quote',params=params).status_code==409


def test_unknown_provider_category_and_closed_markets_are_safe():
    rows=[market('new-topic','Science'),{**market('closed','sports'),'market_state':'closed'}, {**market('past','sports'),'closes_at':'2000-01-01T00:00:00Z'}]
    result=order_markets(rows,history_weights([],[]))
    assert [m['id'] for m in result]==['new-topic']
    assert result[0]['topic_history']['weight']==0
