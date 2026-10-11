import uuid
from datetime import datetime,timezone
from sqlalchemy import create_engine,String,Integer,Boolean,JSON,ForeignKey,UniqueConstraint,event
from sqlalchemy.orm import DeclarativeBase,Mapped,mapped_column,Session

def uid(): return str(uuid.uuid4())
def timestamp(): return datetime.now(timezone.utc).isoformat()
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__='users'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    name:Mapped[str]=mapped_column(String)
    interests:Mapped[list]=mapped_column(JSON)
    weekly_cap_cents:Mapped[int]=mapped_column(Integer)
    paused:Mapped[bool]=mapped_column(Boolean,default=False)
class Pot(Base):
    __tablename__='pots'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),primary_key=True)
    savings_cents:Mapped[int]=mapped_column(Integer,default=0)
    rollover_cents:Mapped[int]=mapped_column(Integer,default=0)
class Purchase(Base):
    __tablename__='transactions'
    __table_args__=(UniqueConstraint('user_id','source','source_id'),)
    id:Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    amount_cents:Mapped[int]=mapped_column(Integer)
    merchant:Mapped[str]=mapped_column(String)
    category:Mapped[str]=mapped_column(String,default='')
    source:Mapped[str]=mapped_column(String,default='manual')
    source_id:Mapped[str|None]=mapped_column(String,nullable=True)
    created_at:Mapped[str]=mapped_column(String,default=timestamp)
    notice:Mapped[str|None]=mapped_column(String,nullable=True)
class Roundup(Base):
    __tablename__='roundups'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    purchase_id:Mapped[str]=mapped_column(ForeignKey('transactions.id'),unique=True)
    amount_cents:Mapped[int]=mapped_column(Integer)
    allocation:Mapped[str]=mapped_column(String,default='pending')
    market_title:Mapped[str|None]=mapped_column(String,nullable=True)
    allocated_at:Mapped[str|None]=mapped_column(String,nullable=True)
class Position(Base):
    __tablename__='positions'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    roundup_id:Mapped[str]=mapped_column(ForeignKey('roundups.id'),unique=True)
    market_id:Mapped[str]=mapped_column(String)
    event_ticker:Mapped[str]=mapped_column(String)
    title:Mapped[str]=mapped_column(String)
    category:Mapped[str]=mapped_column(String)
    outcome:Mapped[str]=mapped_column(String)
    quantity:Mapped[int]=mapped_column(Integer)
    entry_price:Mapped[str]=mapped_column(String)
    cost_cents:Mapped[int]=mapped_column(Integer)
    fee_cents:Mapped[int]=mapped_column(Integer)
    status:Mapped[str]=mapped_column(String,default='open')
    payout_cents:Mapped[int]=mapped_column(Integer,default=0)
    created_at:Mapped[str]=mapped_column(String,default=timestamp)
    mode:Mapped[str]=mapped_column(String,default='paper')
class SandboxOrder(Base):
    __tablename__='sandbox_orders'
    id:Mapped[str]=mapped_column(String,primary_key=True,default=uid)
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    roundup_id:Mapped[str]=mapped_column(ForeignKey('roundups.id'),unique=True)
    market:Mapped[dict]=mapped_column(JSON)
    quote:Mapped[dict]=mapped_column(JSON)
    reserved_cents:Mapped[int]=mapped_column(Integer)
    exchange_id:Mapped[str|None]=mapped_column(String,nullable=True)
    status:Mapped[str]=mapped_column(String,default='submitting')
    message:Mapped[str|None]=mapped_column(String,nullable=True)
    created_at:Mapped[str]=mapped_column(String,default=timestamp)
class PlaidItem(Base):
    __tablename__='plaid_items'
    item_id:Mapped[str]=mapped_column(String,primary_key=True)
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),unique=True)
    access_token:Mapped[str]=mapped_column(String)
    cursor:Mapped[str]=mapped_column(String,default='')

def build_engine(url):
    engine=create_engine(url,connect_args={'check_same_thread':False,'timeout':30})
    @event.listens_for(engine,'connect')
    def configure(dbapi_connection,record):
        cursor=dbapi_connection.cursor(); cursor.execute('PRAGMA foreign_keys=ON'); cursor.execute('PRAGMA journal_mode=WAL'); cursor.close()
    Base.metadata.create_all(engine)
    return engine
