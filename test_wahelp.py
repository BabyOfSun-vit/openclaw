# test_wahelp.py

from pprint import pprint
from typing import Any, Dict, List

from wahelp_client import WahelpClient

# Номер канала из списка, который будем читать
CHANNEL_INDEX = 0

# Сколько последних сообщений вытаскивать
MESSAGES_LIMIT = 30


def extract_channels(raw: Any) -> List[Dict[str, Any]]:
    """
    Универсально достаём список каналов из того,
    что вернул WahelpClient.get_channels().
    """
    print("\n=== RAW CHANNELS RESPONSE TYPE:", type(raw), "=== ")

    # 1) Если это уже список — берём только словари
    if isinstance(raw, list):
        chans = [c for c in raw if isinstance(c, dict)]
        print(f"Парсим как list -> {len(chans)} каналов")
        return chans

    # 2) Если это словарь — пытаемся найти внутри списки
    if isinstance(raw, dict):
        # самый частый вариант: {"success": true, "data": [ ... ]}
        if isinstance(raw.get("data"), list):
            chans = [c for c in raw["data"] if isinstance(c, dict)]
            print(f"Парсим raw['data'] -> {len(chans)} каналов")
            return chans

        # {"success": true, "results": [ ... ]}
        if isinstance(raw.get("results"), list):
            chans = [c for c in raw["results"] if isinstance(c, dict)]
            print(f"Парсим raw['results'] -> {len(chans)} каналов")
            return chans

        # {"channels": [ ... ]}
        if isinstance(raw.get("channels"), list):
            chans = [c for c in raw["channels"] if isinstance(c, dict)]
            print(f"Парсим raw['channels'] -> {len(chans)} каналов")
            return chans

        # {"success": true, "data": {"items": [ ... ]}}
        data = raw.get("data")
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            chans = [c for c in data["items"] if isinstance(c, dict)]
            print(f"Парсим raw['data']['items'] -> {len(chans)} каналов")
            return chans

    # 3) Если формат неожиданный — покажем и вернём пустой список
    print("\n[ОШИБКА] Неожиданный формат ответа get_channels():")
    pprint(raw)
    return []


def main() -> None:
    client = WahelpClient()

    # 1) Логинимся
    client.login()

    # 2) Получаем "сырой" список каналов проекта
    raw_channels = client.get_channels()
    print("\n=== СЫРОЙ ОТВЕТ get_channels() ===")
    pprint(raw_channels)

    # 2.1) Преобразуем к аккуратному списку каналов
    channels = extract_channels(raw_channels)

    print("\n=== СПИСОК КАНАЛОВ (после разбора) ===")
    for i, ch in enumerate(channels):
        # ch уже гарантированно dict, но на всякий случай проверим
        if not isinstance(ch, dict):
            print(f"[{i}] ПРОПУЩЕН (тип {type(ch)})")
            continue

        ch_type = ch.get("type")
        ch_name = ch.get("name") or ch.get("title")
        ch_uuid = ch.get("uuid") or ch.get("id")

        print(f"[{i}] type={ch_type}  name={ch_name}  uuid={ch_uuid}")

    if not channels:
        print("\nКаналов нет, прекращаем.")
        return

    if CHANNEL_INDEX < 0 or CHANNEL_INDEX >= len(channels):
        print(
            f"\nCHANNEL_INDEX={CHANNEL_INDEX} вне диапазона. "
            f"Всего каналов: {len(channels)}. "
            f"Поставь правильный номер канала вверху файла."
        )
        return

    # 3) Берём выбранный канал
    ch = channels[CHANNEL_INDEX]
    if not isinstance(ch, dict):
        print("\n[ОШИБКА] Выбранный канал не является словарём:")
        print(ch)
        return

    channel_uuid = ch.get("uuid") or ch.get("id")
    print(
        f"\n=== БУДЕМ ЧИТАТЬ СООБЩЕНИЯ ИЗ КАНАЛА [{CHANNEL_INDEX}] "
        f"{ch.get('name') or ch.get('title')} (uuid={channel_uuid}) ==="
    )

    if not channel_uuid:
        print("[ОШИБКА] У выбранного канала нет uuid/id, не можем читать сообщения.")
        return

    # 4) Получаем сообщения
    messages = client.get_messages(channel_uuid=channel_uuid, limit=MESSAGES_LIMIT)

    print("\n=== СЫРЫЕ ДАННЫЕ MESSAGES ===")
    pprint(messages)

    # 5) Приводим к списку сообщений
    if isinstance(messages, dict):
        msg_list = (
            messages.get("data")
            or messages.get("results")
            or messages.get("messages")
            or []
        )
    elif isinstance(messages, list):
        msg_list = messages
    else:
        print("\n[ОШИБКА] Неожиданный формат messages:")
        pprint(messages)
        return

    # фильтруем только словари
    msg_list = [m for m in msg_list if isinstance(m, dict)]

    print(f"\nНайдено сообщений: {len(msg_list)}")

    # 6) Ищем последнее входящее сообщение
    incoming = None
    for msg in reversed(msg_list):
        # на всякий случай — но msg уже dict
        if not isinstance(msg, dict):
            continue

        # в разных API это может быть destination/from, direction, is_incoming и т.п.
        destination = msg.get("destination")
        direction = msg.get("direction")
        is_incoming = msg.get("is_incoming")

        if destination == "from" or direction == "incoming" or is_incoming:
            incoming = msg
            break

    if not incoming:
        print("\nВходящих сообщений не найдено.")
        return

    print("\n=== НАЙДЕНО ПОСЛЕДНЕЕ ВХОДЯЩЕЕ СООБЩЕНИЕ ===")
    pprint(incoming)

    # 7) Берём user_id
    user_id = None
    if isinstance(incoming.get("user"), dict):
        user_id = incoming["user"].get("id")
    if not user_id:
        user_id = incoming.get("user_id")

    if not user_id:
        print("\n[ОШИБКА] Не удалось вытащить user_id из сообщения, не можем ответить.")
        return

    # 8) Отправляем тестовый ответ
    text = "Спасибо за ваше сообщение! Это тестовый автответчик 🧡"

    print(f"\nПробуем отправить ответ пользователю user_id={user_id} ...")
    resp = client.send_message(
        channel_uuid=channel_uuid,
        user_id=user_id,
        text=text,
    )
    print("\n=== ОТВЕТ send_message ===")
    pprint(resp)
    print("\nГотово: тестовый ответ отправлен (если ошибок нет выше).")


if __name__ == "__main__":
    main()