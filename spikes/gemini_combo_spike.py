"""Verify Gemini combos using sandbox only. Private checks require sandbox keys.

No mutation occurs without --create or --place-test-order. An actual test
order additionally requires an exclusive journal file so rerunning the same
attempt cannot accidentally place it twice. This spike is not an RFQ taker.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
from app.combos import SandboxCombos, classify_combo_order, combo_legs
from app.providers import Gemini, ProviderError, ProviderRejected, http_json


def emit(value):
    print(json.dumps(value, indent=2, default=str), flush=True)


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-only", action="store_true", help="Read sandbox combo discovery without any account call.")
    parser.add_argument("--leg", action="append", default=[], metavar="CONTRACT_ID:yes|no", help="Verified decimal underlying contract ID; supply 2–6 times.")
    parser.add_argument("--create", action="store_true", help="Create or retrieve one canonical combo; does not place an order.")
    parser.add_argument("--place-test-order", action="store_true", help="Explicitly create the combo and submit ONE sandbox FOK order.")
    parser.add_argument("--quantity", help="Whole contract quantity, required for test order or status lookup.")
    parser.add_argument("--limit-price", help="Explicit authorized combo limit price, required for test order or lookup.")
    parser.add_argument("--journal", type=Path, help="New local JSON file, required for order placement; never reused to place again.")
    parser.add_argument("--order-id", help="Read-only reconcile a known order ID, with --symbol, --quantity and --limit-price.")
    parser.add_argument("--symbol", help="Provider's actual combo instrument symbol, for read-only reconciliation.")
    args = parser.parse_args()
    if args.public_only and (args.create or args.place_test_order or args.order_id):
        parser.error("--public-only cannot be combined with account operations")
    if args.place_test_order and (not args.quantity or not args.limit_price or not args.journal):
        parser.error("--place-test-order requires --quantity, --limit-price and a new --journal path")
    if args.order_id and (not args.symbol or not args.quantity or not args.limit_price):
        parser.error("--order-id requires --symbol, --quantity and --limit-price")
    if args.order_id and (args.create or args.place_test_order):
        parser.error("Read-only reconciliation cannot be combined with creation or placement")
    return args


def main():
    args = arguments()
    # Fail before even public discovery by default, so the private test's
    # missing-key result cannot be mistaken for an authenticated API check.
    if not args.public_only and (not os.getenv("GEMINI_API_KEY") or not os.getenv("GEMINI_API_SECRET")):
        emit({"sandbox_combo_private_test": "not_verified", "reason": "Set GEMINI_API_KEY and GEMINI_API_SECRET from a Gemini sandbox account in .env. No HTTP request was sent.", "public_check": "Run with --public-only for unauthenticated sandbox discovery."})
        return 2
    if args.place_test_order and args.journal.exists():
        emit({"sandbox_combo_test": "not_verified", "reason": "The journal already exists. Reconcile its known order ID; do not repeat an uncertain order. No HTTP request was sent."})
        return 2
    api = SandboxCombos(Gemini(Gemini.SANDBOX))
    try:
        if args.order_id:
            emit(api.status(args.symbol, args.order_id, args.quantity, args.limit_price))
            return 0
        public = http_json("GET", Gemini.SANDBOX + "/v1/prediction-markets/combos", params={"limit": 2})
        records = public.get("combos")
        if not isinstance(records, list):
            raise ProviderError("Sandbox discovery did not return a combo list.")
        emit({"sandbox_combo_discovery": "worked", "checked_at": datetime.now(timezone.utc).isoformat(), "pagination": public.get("pagination"), "sample": [{"contract_id": r.get("contract", {}).get("contractId"), "leg_count": len(r.get("legs", [])), "status": r.get("contract", {}).get("contractStatus")} for r in records]})
        if args.public_only:
            return 0
        if not args.create and not args.place_test_order:
            api.gemini.ensure_trading_ready()
            emit({"sandbox_account_preflight": "worked", "combo_creation": "not_requested", "combo_order": "not_requested"})
            return 0
        legs = []
        for entry in args.leg:
            contract_id, separator, outcome = entry.partition(":")
            if not separator:
                raise ProviderRejected("Each --leg must be a verified CONTRACT_ID:yes or CONTRACT_ID:no.")
            legs.append({"contract_id": contract_id, "outcome": outcome})
        combo_legs(legs)
        response = api.create(legs)
        emit({"sandbox_combo_creation": "worked", "response": response, "combo_order": "not_requested" if not args.place_test_order else "pending_submission"})
        if not args.place_test_order:
            return 0
        combo = response["combo"]
        attempt = {"state": "submitting", "environment": "Gemini sandbox", "symbol": combo.get("instrumentSymbol"), "quantity": args.quantity, "limit_price": args.limit_price, "created_at": datetime.now(timezone.utc).isoformat()}
        # Exclusive creation prevents the same documented attempt being rerun.
        args.journal.parent.mkdir(parents=True, exist_ok=True)
        try:
            with args.journal.open("x") as handle:
                json.dump(attempt, handle, indent=2)
        except FileExistsError:
            raise ProviderRejected("The journal already exists. Reconcile its known order ID; do not repeat an uncertain order.") from None
        try:
            order = api.place(combo, args.quantity, args.limit_price)
            classified = classify_combo_order(order, args.quantity, args.limit_price)
            attempt.update(classified)
            # An accepted OPEN order is reconciled, never resubmitted.
            if classified["state"] == "unknown" and classified.get("order_id"):
                try:
                    attempt.update(api.status(combo["instrumentSymbol"], classified["order_id"], args.quantity, args.limit_price))
                except ProviderError as exc:
                    attempt["reconciliation_error"] = str(exc)
        except ProviderRejected as exc:
            attempt.update(state="rejected", error=str(exc))
        except ProviderError as exc:
            attempt.update(state="unknown", error=str(exc), next_step="Inspect the sandbox account and reconcile; do not place this attempt again.")
        args.journal.write_text(json.dumps(attempt, indent=2, default=str) + "\n")
        emit({"sandbox_combo_order": attempt["state"], "journal": str(args.journal), "attempt": attempt})
        return 0 if attempt["state"] == "filled" else 3
    except (ProviderError, OSError) as exc:
        emit({"sandbox_combo_test": "not_verified", "reason": str(exc)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
