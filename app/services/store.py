"""
Store / Checkout service – Section 5.12 + NFR-3
Concurrency-safe inventory with reservation.
"""

from __future__ import annotations

import base64
import io
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.core import Variant, DiscountCode, AppState
from app.utils.errors import (
    validation_error, not_found, conflict, ApiError
)
from app.utils.validation import valid_id, is_int
from app.utils.signing import sign_record, canonical
from app.config import DAY1_SALT


# Very simple in-memory mock payment gateway
def mock_payment(token: str) -> dict:
    if token == "tok_success":
        return {"authorization_id": "auth_1", "capture_id": "cap_1", "state": "captured"}
    if token == "tok_declined":
        raise ApiError(402, "PAYMENT_DECLINED", "Payment was declined by the mock gateway.")
    if token == "tok_capture_fail":
        raise ApiError(402, "PAYMENT_CAPTURE_FAILED", "Authorization succeeded but capture failed.")
    raise ApiError(402, "PAYMENT_DECLINED", "Unknown payment token.")


def get_inventory(variant_id: str) -> dict:
    with SessionLocal() as db:
        variant = db.get(Variant, variant_id)
        if not variant:
            raise not_found("VARIANT_NOT_FOUND", f"Variant {variant_id} not found")
        return {
            "variant_id": variant_id,
            "stock": variant.stock,
            "reserved": variant.reserved,
        }


def checkout(body: dict) -> tuple[int, dict]:
    """
    Returns (status_code, response_body)
    """
    order_id = body.get("order_id")
    customer_id = body.get("customer_id")
    items = body.get("items")
    discount_code = body.get("discount_code")
    payment = body.get("payment") or {}

    # ---------- 1. Validation ----------
    if not valid_id(order_id):
        raise validation_error(["order_id"])
    if not isinstance(customer_id, str) or not customer_id:
        raise validation_error(["customer_id"])
    if not isinstance(items, list) or not (1 <= len(items) <= 10):
        raise validation_error(["items"])

    seen_variants = set()
    parsed_items = []
    for it in items:
        if not isinstance(it, dict):
            raise validation_error(["items"])
        vid = it.get("variant_id")
        qty = it.get("quantity")
        if not valid_id(vid) or not is_int(qty) or not (1 <= qty <= 10):
            raise validation_error(["items"])
        if vid in seen_variants:
            raise validation_error(["items"], "duplicate variant_id")
        seen_variants.add(vid)
        parsed_items.append({"variant_id": vid, "quantity": qty})

    token = payment.get("token")
    if not isinstance(token, str):
        raise validation_error(["payment.token"])

    # ---------- 2. Idempotency check ----------
    with SessionLocal() as db:
        # We store completed orders in AppState for simplicity (key = "order:" + order_id)
        existing = db.get(AppState, f"order:{order_id}")
        if existing:
            stored = existing.value
            # Same body → return stored result
            if (stored.get("customer_id") == customer_id and
                stored.get("items") == parsed_items and
                stored.get("discount_code") == discount_code and
                stored.get("payment_token") == token):
                return 200, stored["response"]
            else:
                raise conflict("DUPLICATE_ORDER_ID", "Order ID already used with different body")

        # ---------- 3. Load variants & check existence ----------
        variants = {}
        for it in parsed_items:
            v = db.get(Variant, it["variant_id"])
            if not v:
                raise not_found("VARIANT_NOT_FOUND", f"Variant {it['variant_id']} not found",
                                variant_id=it["variant_id"])
            variants[it["variant_id"]] = v

        # ---------- 4. Discount ----------
        discount_minor = 0
        if discount_code is not None:
            if discount_code != "WELCOME10":
                raise validation_error(["discount_code"], "Invalid discount code")
            # will calculate after subtotal

        # ---------- 5. Atomic reservation ----------
        # Lock all involved rows in consistent order to avoid deadlocks
        variant_ids = sorted(variants.keys())
        locked = {}
        for vid in variant_ids:
            v = db.execute(
                select(Variant).where(Variant.variant_id == vid).with_for_update()
            ).scalar_one()
            locked[vid] = v

        # Check stock
        for it in parsed_items:
            v = locked[it["variant_id"]]
            if v.stock < it["quantity"]:
                raise conflict("OUT_OF_STOCK",
                               f"Variant {it['variant_id']} has no stock left.",
                               variant_id=it["variant_id"])

        # Reserve
        for it in parsed_items:
            v = locked[it["variant_id"]]
            v.stock -= it["quantity"]
            v.reserved += it["quantity"]

        db.flush()

        # ---------- 6. Call mock payment ----------
        try:
            payment_result = mock_payment(token)
        except ApiError as e:
            # Release reservation
            for it in parsed_items:
                v = locked[it["variant_id"]]
                v.stock += it["quantity"]
                v.reserved -= it["quantity"]
            db.commit()
            raise e

        # ---------- 7. Commit reservation (move from reserved to sold) ----------
        for it in parsed_items:
            v = locked[it["variant_id"]]
            v.reserved -= it["quantity"]
            # stock already decreased

        # Calculate totals
        subtotal = 0
        item_details = []
        for it in parsed_items:
            v = locked[it["variant_id"]]
            line = v.price_minor * it["quantity"]
            subtotal += line
            item_details.append({
                "variant_id": it["variant_id"],
                "quantity": it["quantity"],
                "unit_price_minor": v.price_minor,
            })

        if discount_code == "WELCOME10":
            discount_minor = (subtotal * 10) // 100

        total_minor = subtotal - discount_minor
        paid_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # ---------- 8. Build receipt + signature ----------
        receipt_payload = {
            "order_id": order_id,
            "customer_id": customer_id,
            "items": item_details,
            "subtotal_minor": subtotal,
            "discount_minor": discount_minor,
            "total_minor": total_minor,
            "currency": "PKR",
            "paid_at": paid_at,
        }
        signature = sign_record(order_id, receipt_payload)

        # Simple PDF (minimal valid PDF containing the required text)
        pdf_content = (
            b"%PDF-1.4\n"
            b"1 0 obj<<>>endobj\n"
            b"2 0 obj<< /Length 68 >>stream\n"
            + f"BT /F1 12 Tf 100 700 Td ({order_id}) Tj T* (PKR {total_minor/100:.2f}) Tj ET\n".encode()
            + b"endstream endobj\n"
            b"3 0 obj<< /Type /Page /Parent 4 0 R /Contents 2 0 R >>endobj\n"
            b"4 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
            b"5 0 obj<< /Type /Catalog /Pages 4 0 R >>endobj\n"
            b"xref\n0 6\n0000000000 65535 f \ntrailer<< /Size 6 /Root 5 0 R >>\nstartxref\n0\n%%EOF"
        )
        pdf_base64 = base64.b64encode(pdf_content).decode("ascii")

        response = {
            "order_id": order_id,
            "status": "paid",
            "currency": "PKR",
            "items": item_details,
            "subtotal_minor": subtotal,
            "discount_minor": discount_minor,
            "total_minor": total_minor,
            "payment": payment_result,
            "receipt": {
                "payload": receipt_payload,
                "signature": signature,
                "pdf_base64": pdf_base64,
            },
        }

        # Store for idempotency
        db.add(AppState(
            key=f"order:{order_id}",
            value={
                "customer_id": customer_id,
                "items": parsed_items,
                "discount_code": discount_code,
                "payment_token": token,
                "response": response,
            }
        ))
        db.commit()

        return 201, response