"""Controlled transport checks; these are not evidence of a live private fill."""
import base64
import json
import runpy
import sys
from pathlib import Path

import pytest

from app import providers
from app.combos import SandboxCombos, combo_legs, classify_combo_order
from app.providers import Gemini, ProviderError, ProviderRejected


LEGS = [
    {"contract_id": "101", "outcome": "yes"},
    {"contract_id": "202", "outcome": "no"},
]
COMBO = {
    "id": 456,
    "instrumentSymbol": "GEMI-CMB-0526-A7F3B2C1D4E5",
    "instrumentRegistered": True,
    "status": "Active",
    "legCount": 2,
    "legs": [
        {"contractId": "101", "requiredOutcome": "Yes"},
        {"contractId": "202", "requiredOutcome": "No"},
    ],
}


def transport(monkeypatch, replies):
    monkeypatch.setenv("GEMINI_API_KEY", "controlled-sandbox-key")
    monkeypatch.setenv("GEMINI_API_SECRET", "controlled-secret")
    calls = []

    def request(method, url, **kwargs):
        assert url.startswith(Gemini.SANDBOX + "/")
        assert kwargs["content"] == b""
        payload = json.loads(base64.b64decode(kwargs["headers"]["X-GEMINI-PAYLOAD"]))
        calls.append((method, url, payload))
        reply = replies[len(calls) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(providers, "http_json", request)
    return calls


def test_create_preserves_required_outcomes_and_uses_signed_sandbox_endpoint(monkeypatch):
    calls = transport(monkeypatch, [{"hasAcceptedLatest": True}, {"combo": COMBO, "alreadyExisted": False}])
    result = SandboxCombos(Gemini(Gemini.SANDBOX)).create(LEGS)
    assert result["combo"]["instrumentSymbol"] == COMBO["instrumentSymbol"]
    assert calls[-1][2]["legs"] == [
        {"contractId": "101", "requiredOutcome": "Yes"},
        {"contractId": "202", "requiredOutcome": "No"},
    ]
    assert calls[-1][1] == Gemini.SANDBOX + "/v1/prediction-markets/combos"


@pytest.mark.parametrize("legs", [
    LEGS[:1], LEGS * 4,
    [{"contract_id": "101", "outcome": "yes"}, {"contract_id": "101", "outcome": "no"}],
    [{"contract_id": "203737-295784", "outcome": "yes"}, LEGS[1]],
    [{"contract_id": "101", "outcome": "maybe"}, LEGS[1]],
    [{"market_id": "GEMI-X", "outcome": "yes"}, LEGS[1]],
])
def test_invalid_or_ambiguous_legs_never_send_request(monkeypatch, legs):
    calls = transport(monkeypatch, [])
    with pytest.raises(ProviderRejected):
        SandboxCombos(Gemini(Gemini.SANDBOX)).create(legs)
    assert calls == []


def test_production_feed_fails_before_private_call(monkeypatch):
    calls = transport(monkeypatch, [])
    with pytest.raises(ProviderRejected, match="sandbox"):
        SandboxCombos(Gemini()).create(LEGS)
    assert calls == []


def test_missing_keys_fails_actionably_before_network(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_SECRET", raising=False)
    monkeypatch.setattr(providers, "http_json", lambda *a, **k: pytest.fail("must not send"))
    with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
        SandboxCombos(Gemini(Gemini.SANDBOX)).create(LEGS)


def test_changed_provider_leg_set_cannot_be_used_as_requested_combo(monkeypatch):
    wrong = {**COMBO, "legs": [{"contractId": "101", "requiredOutcome": "Yes"}, {"contractId": "303", "requiredOutcome": "No"}]}
    calls = transport(monkeypatch, [{"hasAcceptedLatest": True}, {"combo": wrong, "alreadyExisted": True}])
    with pytest.raises(ProviderError, match="leg"):
        SandboxCombos(Gemini(Gemini.SANDBOX)).create(LEGS)
    assert len(calls) == 2


def test_one_combo_order_never_places_individual_legs(monkeypatch):
    calls = transport(monkeypatch, [{"hasAcceptedLatest": True}, {"orderId": 789, "symbol": COMBO["instrumentSymbol"], "status": "open"}])
    SandboxCombos(Gemini(Gemini.SANDBOX)).place(COMBO, "2", "0.45")
    assert len(calls) == 2
    assert calls[-1][2] == {
        "request": "/v1/prediction-markets/order", "nonce": calls[-1][2]["nonce"],
        "symbol": COMBO["instrumentSymbol"], "orderType": "limit", "side": "buy",
        "outcome": "yes", "quantity": "2", "price": "0.45",
        "timeInForce": "fill-or-kill", "makerOrCancel": False,
    }


@pytest.mark.parametrize("quantity,price", [("0.5", ".45"), ("-1", ".45"), ("1", "NaN"), ("1", "1"), ("1", ".455")])
def test_bad_size_and_limit_fail_without_network(monkeypatch, quantity, price):
    calls = transport(monkeypatch, [])
    with pytest.raises(ProviderRejected):
        SandboxCombos(Gemini(Gemini.SANDBOX)).place(COMBO, quantity, price)
    assert calls == []


def test_unregistered_combo_is_not_orderable(monkeypatch):
    calls = transport(monkeypatch, [])
    with pytest.raises(ProviderRejected, match="registered"):
        SandboxCombos(Gemini(Gemini.SANDBOX)).place({**COMBO, "instrumentRegistered": False}, 1, ".45")
    assert calls == []


def test_rejected_and_uncertain_submission_are_not_retried(monkeypatch):
    for failure in (ProviderRejected("Rejected"), ProviderError("Connection lost")):
        calls = transport(monkeypatch, [{"hasAcceptedLatest": True}, failure])
        with pytest.raises(type(failure)):
            SandboxCombos(Gemini(Gemini.SANDBOX)).place(COMBO, 1, ".45")
        assert len(calls) == 2


def test_wrong_submission_symbol_stays_uncertain(monkeypatch):
    calls = transport(monkeypatch, [{"hasAcceptedLatest": True}, {"orderId": 789, "symbol": "GEMI-CMB-OTHER", "status": "filled"}])
    with pytest.raises(ProviderError, match="unverified instrument"):
        SandboxCombos(Gemini(Gemini.SANDBOX)).place(COMBO, 1, ".45")
    assert len(calls) == 2


def test_no_fill_is_inferred_from_acceptance_or_failed_rfq_quantity():
    assert classify_combo_order({"orderId": 1, "status": "open"}, "2", ".45")["state"] == "unknown"
    assert classify_combo_order({"S": "FAILED", "f": "2"}, "2", ".45")["state"] == "unknown"


def test_full_fill_requires_execution_quantity_and_price():
    filled = {"orderId": 1, "status": "filled", "filledQuantity": "2", "remainingQuantity": "0", "avgExecutionPrice": ".44"}
    assert classify_combo_order(filled, "2", ".45")["state"] == "filled"
    assert classify_combo_order({**filled, "filledQuantity": "1"}, "2", ".45")["state"] == "unknown"
    assert classify_combo_order({**filled, "avgExecutionPrice": ".46"}, "2", ".45")["state"] == "unknown"
    assert classify_combo_order({**filled, "avgExecutionPrice": None}, "2", ".45")["state"] == "unknown"


def test_cancelled_zero_fill_can_release_reservation():
    assert classify_combo_order({"orderId": 1, "status": "cancelled", "filledQuantity": "0"}, "2", ".45")["state"] == "cancelled"
    assert classify_combo_order({"orderId": 1, "status": "cancelled", "filledQuantity": "1"}, "2", ".45")["state"] == "unknown"
    assert classify_combo_order({"status": "cancelled", "filledQuantity": "0"}, "2", ".45")["state"] == "unknown"


def test_status_lookup_uses_existing_order_id_and_never_places(monkeypatch):
    calls = transport(monkeypatch, [{"orders": [{"orderId": 789, "symbol": COMBO["instrumentSymbol"], "status": "cancelled", "filledQuantity": "0"}]}])
    result = SandboxCombos(Gemini(Gemini.SANDBOX)).status(COMBO["instrumentSymbol"], "789", "2", ".45")
    assert result["state"] == "cancelled"
    assert all("/order" != call[1].removeprefix(Gemini.SANDBOX + "/v1/prediction-markets") for call in calls)


def test_private_spike_missing_keys_fails_before_any_http(monkeypatch, capsys):
    module = runpy.run_path(str(Path(__file__).resolve().parents[2] / "spikes" / "gemini_combo_spike.py"))
    monkeypatch.setattr(sys, "argv", ["gemini_combo_spike.py"])
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_SECRET", raising=False)
    monkeypatch.setattr(providers, "http_json", lambda *a, **k: pytest.fail("must not send"))
    monkeypatch.setitem(module["main"].__globals__, "http_json", lambda *a, **k: pytest.fail("must not send"))
    assert module["main"]() == 2
    output = json.loads(capsys.readouterr().out)
    assert output["sandbox_combo_private_test"] == "not_verified"
    assert "No HTTP request was sent" in output["reason"]


def test_reusing_spike_order_journal_fails_before_any_http(monkeypatch, tmp_path, capsys):
    module = runpy.run_path(str(Path(__file__).resolve().parents[2] / "spikes" / "gemini_combo_spike.py"))
    journal = tmp_path / "attempt.json"
    journal.write_text('{"state":"unknown"}')
    monkeypatch.setattr(sys, "argv", ["gemini_combo_spike.py", "--place-test-order", "--quantity", "1", "--limit-price", ".45", "--journal", str(journal)])
    monkeypatch.setenv("GEMINI_API_KEY", "controlled-key")
    monkeypatch.setenv("GEMINI_API_SECRET", "controlled-secret")
    monkeypatch.setattr(providers, "http_json", lambda *a, **k: pytest.fail("must not send"))
    monkeypatch.setitem(module["main"].__globals__, "http_json", lambda *a, **k: pytest.fail("must not send"))
    assert module["main"]() == 2
    assert "No HTTP request was sent" in json.loads(capsys.readouterr().out)["reason"]
    assert json.loads(journal.read_text())["state"] == "unknown"
