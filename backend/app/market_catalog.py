"""Group real Gemini side quotes into events and tradeable contracts."""
from decimal import Decimal

from .scoring import topic_for


def _buy_price(row):
    if row is None or row.get('price') is None:
        return None
    try:
        price = Decimal(str(row['price']))
        if not price.is_finite() or not 0 < price < 1:
            return None
    except (ValueError, TypeError, ArithmeticError):
        return None
    return str(row['price'])


def event_catalog(markets, query=None):
    """Keep each contract's actual Yes/No buy quotes, never complementary prices.

    Search is applied after grouping so a matching label retains the event's
    other contracts. Contract IDs remain the Gemini instrument symbols used
    by quote and allocation endpoints.
    """
    grouped = {}
    for row in markets:
        ticker, symbol, side = row.get('event_ticker'), row.get('id'), row.get('outcome')
        if not ticker or not symbol or side not in ('yes', 'no'):
            continue
        grouped.setdefault(ticker, {}).setdefault(symbol, {})[side] = row

    events = []
    needle = (query or '').strip().casefold()
    for ticker, instruments in grouped.items():
        contracts = []
        for symbol, sides in instruments.items():
            base = sides.get('yes') or sides['no']
            contract = {key: value for key, value in base.items()
                        if key not in ('outcome', 'price', 'sell_price')}
            yes, no = _buy_price(sides.get('yes')), _buy_price(sides.get('no'))
            contract.update(id=symbol, event_ticker=ticker,
                            title=base.get('title', ''), label=base.get('label', ''),
                            category=base.get('category', ''),
                            topic=base.get('topic') or topic_for(base.get('category') or ''),
                            prices={'yes': yes, 'no': no},
                            implied_probability=float(yes) if yes is not None else None)
            contracts.append(contract)
        first = contracts[0]
        contracts.sort(key=lambda contract: (
            contract['implied_probability'] is None,
            -(contract['implied_probability'] or 0),
            contract['id'],
        ))
        event = {'id': ticker, 'title': first['title'], 'category': first['category'],
                 'topic': first['topic'], 'closes_at': first.get('closes_at'),
                 'source': 'gemini', 'outcomes': contracts}
        searchable = [event['title'], event['category'], event['topic']]
        searchable.extend(value for contract in contracts
                          for value in (contract['title'], contract['label'], contract['category']))
        if not needle or any(needle in str(value or '').casefold() for value in searchable):
            events.append(event)
    return events
