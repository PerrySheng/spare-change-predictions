"""Identify purchase entries and readable names from actual Plaid fields."""
import re

NON_PURCHASE_CATEGORIES = {'BANK_FEES', 'LOAN_PAYMENTS', 'TRANSFER_OUT', 'TRANSFER_IN', 'INCOME'}
FINANCIAL_NAME = re.compile(r'^(?:interest(?:\s+(?:charged|charges?|payment))?|(?:bank|overdraft|late)\s+fees?|credit\s+card\s+payment)(?:\s*[-:(].*)?$', re.I)
DEMO_NAME = re.compile(r'^Spare demo [\w-]+:\s*(.+)$')

def clean_name(value):
    return ' '.join(value.split())[:160] if isinstance(value, str) else ''

def is_purchase_entry(merchant, category, source='plaid'):
    if source != 'plaid': return True
    return str(category or '').strip().upper() not in NON_PURCHASE_CATEGORIES and not FINANCIAL_NAME.fullmatch(clean_name(merchant))

def plaid_purchase_name(transaction):
    for field in ('original_description', 'name'):
        match = DEMO_NAME.fullmatch(clean_name(transaction.get(field)))
        if match: return clean_name(match.group(1))
    for field in ('merchant_name', 'name', 'original_description'):
        value = clean_name(transaction.get(field))
        if value: return value
    category = (transaction.get('personal_finance_category') or {}).get('primary', '')
    return (str(category).replace('_', ' ').title() + ' purchase') if category else 'Purchase'

def is_demo_purchase(transaction, batch):
    prefix = f'Spare demo {batch}:'
    return any(str(transaction.get(field) or '').startswith(prefix) for field in ('original_description', 'name'))
