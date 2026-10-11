"""USD input and accounting. Amounts in the database are integer cents."""
import re
from decimal import Decimal, ROUND_CEILING
import os
TAKER_RATE=Decimal(os.getenv('GEMINI_TAKER_RATE','0.07'))
def parse_cents(value):
    raw=re.sub(r'^(?:USD\s*|\$\s*)','',str(value).strip(),flags=re.I)
    if not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?',raw):
        raise ValueError('Enter a USD amount, for example $4.63. Use a dot for decimals.')
    cents=int(Decimal(raw.replace(',',''))*100)
    if not 0<cents<=100_000_000: raise ValueError('Amount must be between $0.01 and $1,000,000.')
    return cents
def roundup_cents(cents): return (-cents)%100
def fee_cents(quantity,price):
    return int((TAKER_RATE*quantity*price*(1-price)*100).to_integral_value(rounding=ROUND_CEILING))
def order_quote(budget,price,quantity_minimum=Decimal('1'),quantity_increment=Decimal('1'),max_quantity=None):
    price=Decimal(str(price)); minimum=Decimal(str(quantity_minimum)); increment=Decimal(str(quantity_increment))
    if not 0<price<1 or increment<=0 or minimum<=0: raise ValueError('Contract has no valid executable price or quantity grid.')
    q=int(Decimal(budget)/(price*100))
    if max_quantity is not None: q=min(q,max_quantity)
    while q>0:
        cost=int((q*price*100).to_integral_value(rounding=ROUND_CEILING)); fee=fee_cents(q,price)
        if Decimal(q)>=minimum and Decimal(q)%increment==0 and cost+fee<=budget:
            return {'quantity':q,'cost_cents':cost,'fee_cents':fee,'total_cents':cost+fee,'leftover_cents':budget-cost-fee}
        q-=1
    return {'quantity':0,'cost_cents':0,'fee_cents':0,'total_cents':0,'leftover_cents':budget}
