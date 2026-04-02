from __future__ import annotations

import logging
from typing import Any

import httpx

from nouse.ingress.allowlist import approve_pairing, is_allowed, request_pairing

log = logging.getLogger("nouse.ingress.telegram")


def _api_url(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def poll_telegram_updates(
    *,
    token: str,
    offset: int = 0,
    timeout_sec: int = 8,
    limit: int = 20,
) -> dict[str, Any]:
    params = {
        "offset": int(offset),
        "timeout": max(1, int(timeout_sec)),
        "limit": max(1, min(int(limit), 100)),
    }
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(_api_url(token, "getUpdates"), params=params)
        resp.raise_for_status()
        payload = resp.json()
    if not isinstance(payload, dict):
        return {"ok": False, "result": []}
    return payload


def _send_telegram_message(token: str, chat_id: str, text: str) -> None:
    msg = str(text or "").strip()
    if not msg:
        return
    try:
        with httpx.Client(timeout=20.0) as client:
            client.post(
                _api_url(token, "sendMessage"),
                json={"chat_id": chat_id, "text": msg[:3900]},
            )
    except Exception as e:
        log.warning("Kunde inte skicka Telegram-svar: %s", e)


def _extract_message(update: dict[str, Any]) -> dict[str, str] | None:
    msg = update.get("message") or update.get("edited_message")
    if not isinstance(msg, dict):
        return None
    text = str(msg.get("text") or "").strip()
    chat = msg.get("chat") or {}
    user = msg.get("from") or {}
    chat_id = str(chat.get("id") or "").strip()
    user_id = str(user.get("id") or "").strip()
    if not chat_id or not text:
        return None
    return {"chat_id": chat_id, "user_id": user_id, "text": text}


def ingest_telegram_once(
    *,
    token: str,
    daemon_base: str = "http://127.0.0.1:8765",
    offset: int = 0,
    timeout_sec: int = 8,
    limit: int = 20,
    strict_pairing: bool = True,
) -> dict[str, Any]:
    payload = poll_telegram_updates(
        token=token,
        offset=offset,
        timeout_sec=timeout_sec,
        limit=limit,
    )
    rows = payload.get("result") if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []
    processed = 0
    rejected = 0
    answered = 0
    next_offset = int(offset)

    for item in rows:
        if not isinstance(item, dict):
            continue
        update_id = int(item.get("update_id", 0) or 0)
        if update_id > 0:
            next_offset = max(next_offset, update_id + 1)
        msg = _extract_message(item)
        if not msg:
            continue
        processed += 1
        chat_id = msg["chat_id"]
        user_id = msg["user_id"] or chat_id
        text = msg["text"]

        if text.lower().startswith("/pair "):
            code = text.split(" ", 1)[1].strip().upper()
            approved = approve_pairing("telegram", code)
            if approved:
                _send_telegram_message(token, chat_id, "Pairing godkänd. Du är nu allowlistad.")
            else:
                _send_telegram_message(token, chat_id, "Ogiltig pairing-kod.")
            continue

        if strict_pairing and not is_allowed("telegram", user_id):
            pairing = request_pairing("telegram", user_id)
            _send_telegram_message(
                token,
                chat_id,
                (
                    "Du är inte pairad ännu.\n"
                    f"Skicka `/pair {pairing['code']}` för att bli godkänd."
                ),
            )
            rejected += 1
            continue

        try:
            with httpx.Client(timeout=90.0) as client:
                resp = client.post(
                    f"{daemon_base.rstrip('/')}/api/chat",
                    json={
                        "query": text,
                        "session_id": f"telegram_{chat_id}",
                    },
                )
                resp.raise_for_status()
                out = resp.json()
            answer = str(out.get("response") or "").strip()
            if answer:
                _send_telegram_message(token, chat_id, answer)
                answered += 1
        except Exception as e:
            log.warning("Telegram ingress kunde inte anropa /api/chat: %s", e)
            _send_telegram_message(token, chat_id, "Internt fel i b76 ingress.")

    return {
        "ok": True,
        "processed": processed,
        "rejected": rejected,
        "answered": answered,
        "next_offset": next_offset,
        "updates": len(rows),
    }
