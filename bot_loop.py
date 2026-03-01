#!/usr/bin/env python3
# bot_loop.py — основной цикл-бот для Wahelp + ChatGPT

from assistant_brain import process_message
import os
import time
import sqlite3
from typing import Any, Dict, List

from wahelp_client import WahelpClient

# === НАСТРОЙКИ ===

CHANNEL_INDEX = 0
POLL_INTERVAL = 15
MESSAGES_LIMIT = 30

STATE_DB_PATH = os.environ.get("STATE_DB_PATH", "/root/wahelp_state.sqlite3")


# === SQLITE ===

def init_state_db() -> sqlite3.Connection:
    conn = sqlite3.connect(STATE_DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS last_message (
            channel_uuid TEXT PRIMARY KEY,
            last_id TEXT
        )
        """
    )
    conn.commit()
    return conn


def get_last_id(conn: sqlite3.Connection, channel_uuid: str) -> str | None:
    cur = conn.cursor()
    cur.execute(
        "SELECT last_id FROM last_message WHERE channel_uuid = ?",
        (channel_uuid,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def set_last_id(conn: sqlite3.Connection, channel_uuid: str, msg_id: str) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO last_message (channel_uuid, last_id)
        VALUES (?, ?)
        ON CONFLICT(channel_uuid) DO UPDATE SET last_id = excluded.last_id
        """,
        (channel_uuid, msg_id),
    )
    conn.commit()


# === РАЗБОР СООБЩЕНИЙ ===

def extract_messages(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [m for m in raw if isinstance(m, dict)]

    if isinstance(raw, dict):
        for key in ("data", "results", "messages", "items"):
            val = raw.get(key)
            if isinstance(val, list):
                return [m for m in val if isinstance(m, dict)]
        data = raw.get("data")
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return [m for m in data["items"] if isinstance(m, dict)]

    return []


def is_incoming(msg: Dict[str, Any]) -> bool:
    if msg.get("destination") == "from":
        return True
    if msg.get("direction") == "incoming":
        return True
    if msg.get("is_incoming") is True:
        return True
    return False


def get_message_id(msg: Dict[str, Any]) -> str | None:
    return msg.get("id") or msg.get("uuid") or msg.get("message_id")


def get_user_id_from_msg(msg: Dict[str, Any]) -> int | str | None:
    if isinstance(msg.get("user"), dict):
        return msg["user"].get("id")
    return msg.get("user_id")


# === ОСНОВНОЙ ЦИКЛ ===

def main() -> None:
    print("Стартуем bot_loop...")

    client = WahelpClient()
    client.login()

    conn = init_state_db()

    channels_raw = client.get_channels()

    if isinstance(channels_raw, dict):
        channels = channels_raw.get("data") or channels_raw.get("results") or []
    else:
        channels = channels_raw

    channels = [ch for ch in channels if isinstance(ch, dict)]

    if not channels:
        print("Каналов нет — выходим.")
        return

    if CHANNEL_INDEX >= len(channels):
        print("Неверный CHANNEL_INDEX")
        return

    channel = channels[CHANNEL_INDEX]
    channel_uuid = channel.get("uuid") or channel.get("id")

    if not channel_uuid:
        print("У канала нет uuid — выходим.")
        return

    print(f"Слушаем канал: {channel.get('name') or channel.get('title')}")

    while True:
        try:
            raw = client.get_messages(
                channel_uuid=channel_uuid,
                limit=MESSAGES_LIMIT
            )

            msgs = extract_messages(raw)
            last_id = get_last_id(conn, channel_uuid)

            for msg in msgs:
                mid = get_message_id(msg)
                if not mid:
                    continue

                if last_id and str(mid) <= str(last_id):
                    continue

                if not is_incoming(msg):
                    continue

                user_id = get_user_id_from_msg(msg)
                text = msg.get("text") or msg.get("body") or ""

                if not user_id:
                    continue

                print("\nНовое сообщение:")
                print(text)

                # === ВЫЗОВ ИИ ===
                process_message(
                    msg={
                        "text": text,
                        "channel_uuid": channel_uuid,
                        "user_id": user_id,
                        "phone": msg.get("phone"),
                    },
                    wa_client=client,
                    yc_client=None,  # позже подключим YCLIENTS
                    state=None,
                )

                set_last_id(conn, channel_uuid, str(mid))

        except Exception as e:
            print("\n[ОШИБКА В ЦИКЛЕ]:", e)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()