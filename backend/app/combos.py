"""Gemini's documented canonical-combo workflow, restricted to sandbox.

This is a transport adapter, not an order journal. Callers must persist an
attempt before ``place`` and reconcile uncertainty instead of retrying it.
No documented requester RFQ create/accept methods exist in the reviewed API
or SDK. A combo order is ONE order on the provider's returned combo symbol.
"""
from decimal import Decimal, InvalidOperation
import re

from .providers import Gemini, ProviderError, ProviderRejected


def combo_legs(legs):
    """Convert explicit underlying decimal IDs to Gemini's Yes/No leg shape.

    The current event feed's composite ``id`` is NOT treated as contractId.
    The caller must retain a verified underlying contract ID from the venue.
    """
    if not isinstance(legs, (list, tuple)) or not 2 <= len(legs) <= 6:
        raise ProviderRejected("A Gemini combo requires two to six distinct contract legs.")
    converted = []
    seen = set()
    for leg in legs:
        if not isinstance(leg, dict):
            raise ProviderRejected("Each combo leg needs a verified contract_id and yes/no outcome.")
        contract_id = leg.get("contract_id")
        outcome = leg.get("outcome")
        if not isinstance(contract_id, str) or not re.fullmatch(r"[1-9][0-9]*", contract_id):
            raise ProviderRejected("A combo leg requires Gemini's decimal contract_id; a symbol or composite event ID cannot be guessed.")
        if outcome not in ("yes", "no"):
            raise ProviderRejected("Each combo leg outcome must be yes or no.")
        if contract_id in seen:
            raise ProviderRejected("Each underlying contract can appear only once in a combo.")
        seen.add(contract_id)
        converted.append({"contractId": contract_id, "requiredOutcome": outcome.title()})
    return converted


def _decimal(value):
    if isinstance(value, bool):
        raise InvalidOperation
    result = Decimal(str(value))
    if not result.is_finite():
        raise InvalidOperation
    return result


def _order_values(quantity, limit_price):
    try:
        size = _decimal(quantity)
        price = _decimal(limit_price)
        if size <= 0 or size != size.to_integral_value():
            raise InvalidOperation
        if not Decimal("0.01") <= price <= Decimal("0.99") or price % Decimal("0.01"):
            raise InvalidOperation
    except (InvalidOperation, ValueError, TypeError):
        raise ProviderRejected("Use a positive whole-contract quantity and a combo limit price from $0.01 to $0.99 in $0.01 steps.") from None
    return str(int(size)), format(price, ".2f")


def _symbol(symbol):
    if not isinstance(symbol, str) or len(symbol) > 160 or not re.fullmatch(r"GEMI-CMB-[A-Za-z0-9-]+", symbol):
        raise ProviderRejected("Use the combo instrumentSymbol returned by Gemini; do not construct a ticker locally.")
    return symbol


def classify_combo_order(order, quantity, limit_price):
    """Confirm only a full fill; preserve any ambiguous reservation.

    HTTP acceptance, an OPEN status, and an RFQ's ``f`` field do not prove a
    fill. Fees and settlement are handled by the application's order journal.
    """
    if not isinstance(order, dict):
        return {"state": "unknown", "order": order}
    result = {"state": "unknown", "order_id": str(order["orderId"]) if order.get("orderId") is not None else None, "order": order}
    if result["order_id"] is None or not re.fullmatch(r"[1-9][0-9]*", result["order_id"]):
        return result
    try:
        requested = _decimal(quantity)
        limit = _decimal(limit_price)
        filled = _decimal(order.get("filledQuantity"))
        if order.get("status") == "cancelled" and filled == 0:
            result["state"] = "cancelled"
        elif order.get("status") == "filled" and filled == requested and filled > 0:
            remaining = _decimal(order.get("remainingQuantity"))
            actual_price = _decimal(order.get("avgExecutionPrice"))
            if remaining == 0 and Decimal("0") < actual_price <= limit < Decimal("1"):
                result.update(state="filled", quantity=str(filled), execution_price=str(actual_price))
    except (InvalidOperation, ValueError, TypeError):
        pass
    return result


class SandboxCombos:
    def __init__(self, gemini=None):
        self.gemini = gemini or Gemini(Gemini.SANDBOX)

    def _sandbox(self):
        if self.gemini.base_url != Gemini.SANDBOX:
            raise ProviderRejected("Combo operations require Gemini sandbox market data and sandbox keys.")

    def create(self, legs):
        payload_legs = combo_legs(legs)
        self._sandbox()
        self.gemini.ensure_trading_ready()
        response = self.gemini.private("/v1/prediction-markets/combos", {"legs": payload_legs})
        combo = response.get("combo") if isinstance(response, dict) else None
        if not isinstance(combo, dict) or not isinstance(combo.get("legs"), list):
            raise ProviderError("Gemini did not return a canonical combo leg definition.")
        expected = {(leg["contractId"], leg["requiredOutcome"]) for leg in payload_legs}
        actual = {(str(leg.get("contractId")), leg.get("requiredOutcome")) for leg in combo["legs"] if isinstance(leg, dict)}
        if actual != expected or len(combo["legs"]) != len(payload_legs) or combo.get("legCount") != len(payload_legs):
            raise ProviderError("Gemini's returned combo legs differ from the requested legs.")
        if not isinstance(response.get("alreadyExisted"), bool):
            raise ProviderError("Gemini's canonical combo response is incomplete.")
        return response

    def place(self, combo, quantity, limit_price):
        """Submit once at the explicit authorized limit, with no automatic retry.

        Buying YES on this combo means every leg must meet its required
        outcome. The combo's own price is never calculated from single quotes.
        """
        size, price = _order_values(quantity, limit_price)
        if not isinstance(combo, dict) or combo.get("instrumentRegistered") is not True:
            raise ProviderRejected("The Gemini combo has not been registered as a tradable instrument.")
        symbol = _symbol(combo.get("instrumentSymbol"))
        if combo.get("status") != "Active":
            raise ProviderRejected("The Gemini combo is not active.")
        self._sandbox()
        self.gemini.ensure_trading_ready()
        response = self.gemini.private("/v1/prediction-markets/order", {
            "symbol": symbol, "orderType": "limit", "side": "buy", "outcome": "yes",
            "quantity": size, "price": price, "timeInForce": "fill-or-kill", "makerOrCancel": False,
        })
        if not isinstance(response, dict) or response.get("symbol") != symbol:
            raise ProviderError("The combo submission returned an unverified instrument; inspect the sandbox account before retrying.")
        return response

    def status(self, symbol, order_id, quantity, limit_price):
        self._sandbox()
        symbol = _symbol(symbol)
        if not re.fullmatch(r"[1-9][0-9]*", str(order_id)):
            raise ProviderRejected("A verified Gemini order ID is required to reconcile this combo.")
        order = self.gemini.lookup_order(symbol, order_id)
        if order.get("symbol") != symbol:
            raise ProviderError("The returned order belongs to a different instrument; its reservation remains.")
        return classify_combo_order(order, quantity, limit_price)
