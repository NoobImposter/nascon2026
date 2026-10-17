"""
Offline Sync – Section 5.14
Replays queued actions from a mobile device with conflict resolution.
"""

from __future__ import annotations

from typing import Any

from app.db import SessionLocal
from app.models.core import AppState
from app.services import events as events_svc
from app.services import roster as roster_svc
from app.utils.errors import validation_error
from app.utils.validation import valid_id


def offline_sync(body: dict) -> dict:
    device_id = body.get("device_id")
    actions = body.get("actions")

    if not isinstance(device_id, str) or not device_id:
        raise validation_error(["device_id"])
    if not isinstance(actions, list) or not (1 <= len(actions) <= 100):
        raise validation_error(["actions"])

    # Sort by queued_at ascending (stable for ties)
    try:
        sorted_actions = sorted(
            enumerate(actions),
            key=lambda x: (x[1].get("queued_at", ""), x[0])
        )
    except Exception:
        raise validation_error(["actions"])

    results = [None] * len(actions)
    applied = rejected = duplicate = 0

    with SessionLocal() as db:
        # Track processed (device_id, action_id) for duplicate detection
        processed_key = f"offline:processed:{device_id}"
        processed_state = db.get(AppState, processed_key)
        processed = set(processed_state.value.get("ids", [])) if processed_state else set()

        for original_index, action in sorted_actions:
            action_id = action.get("action_id")
            action_type = action.get("type")
            base_version = action.get("base_version")
            payload = action.get("payload") or {}

            if not valid_id(action_id):
                results[original_index] = {
                    "action_id": action_id,
                    "status": "rejected",
                    "resolution": "server_wins",
                    "error_code": "VALIDATION_ERROR",
                    "processed_order": None,
                    "server_version": None,
                    "signature": None,
                }
                rejected += 1
                continue

            # Duplicate check
            if action_id in processed:
                results[original_index] = {
                    "action_id": action_id,
                    "status": "duplicate",
                    "resolution": "skipped_duplicate",
                    "error_code": None,
                    "processed_order": None,
                    "server_version": None,
                    "signature": None,
                }
                duplicate += 1
                continue

            try:
                if action_type == "score_event":
                    # payload is the same shape as POST /audit/v1/events
                    status, content = events_svc.append_event(payload)

                    # Determine resolution
                    if status == 200:
                        resolution = "skipped_duplicate"
                        status_str = "duplicate"
                        duplicate += 1
                    else:
                        # Check version
                        # For simplicity we treat any successful append as applied/rebased
                        resolution = "rebased_append" if base_version is not None else "appended"
                        status_str = "applied"
                        applied += 1

                    results[original_index] = {
                        "action_id": action_id,
                        "status": status_str,
                        "resolution": resolution,
                        "error_code": None,
                        "processed_order": original_index + 1,
                        "server_version": content.get("match_version"),
                        "signature": content.get("signature"),
                    }

                elif action_type == "roster_transfer":
                    status, content = roster_svc.roster_transfer(payload)

                    if status == 200:
                        resolution = "skipped_duplicate"
                        status_str = "duplicate"
                        duplicate += 1
                    else:
                        resolution = "rebased_append" if base_version is not None else "appended"
                        status_str = "applied"
                        applied += 1

                    results[original_index] = {
                        "action_id": action_id,
                        "status": status_str,
                        "resolution": resolution,
                        "error_code": None,
                        "processed_order": original_index + 1,
                        "server_version": 1,  # simplified
                        "signature": None,
                    }

                else:
                    raise validation_error(["actions"], f"Unknown action type: {action_type}")

                # Mark as processed
                processed.add(action_id)

            except Exception as e:
                # Convert known errors
                error_code = getattr(e, "code", None) or "VALIDATION_ERROR"
                if hasattr(e, "status_code") and e.status_code == 404:
                    error_code = getattr(e, "code", "NOT_FOUND")

                results[original_index] = {
                    "action_id": action_id,
                    "status": "rejected",
                    "resolution": "server_wins",
                    "error_code": error_code,
                    "processed_order": original_index + 1,
                    "server_version": None,
                    "signature": None,
                }
                rejected += 1

        # Save processed set
        db.merge(AppState(key=processed_key, value={"ids": list(processed)}))
        db.commit()

    return {
        "device_id": device_id,
        "results": results,
        "summary": {
            "applied": applied,
            "rejected": rejected,
            "duplicate": duplicate,
        },
    }