#!/usr/bin/env python3
# assistant_brain.py
"""
Логика "мозга" бота для Wahelp.

Сейчас:
- Получает входящее сообщение
- Вызывает ChatGPT (через OpenAI v1 API)
- Возвращает структурированный ответ
- Сам отправляет ответ через wa_client.send_message(...)

В будущем сюда же можно добавить:
- обращение к API YCLIENTS
- аналитику по сообщениям
- разный режим работы по времени и т.п.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from openai import OpenAI

# Инициализация клиента OpenAI (использует переменную окружения OPENAI_API_KEY)
client_ai = OpenAI()

# Базовый системный промпт — кто мы такие и как должны отвечать
SYSTEM_PROMPT = """
Ты ИИ-ассистент Клиники Юлии Сундуловой (премиальный перманентный макияж и врачебная косметология).

ТВОИ ПРАВИЛА:
1. Не придумывай услуги, цены, акции и показания.
2. Всю информацию о процедурах, показаниях и противопоказаниях бери только из базы знаний клиники
   (сайт sundulova.com и внутренние материалы — в коде они появятся позже).
3. Если информации не хватает или есть сомнения — НЕ ВЫДУМЫВАЙ.
   В этом случае:
   - ставь "action": "need_human"
   - пиши в "answer" аккуратный ответ для клиента, что сейчас подключится администратор
   - в "comment_for_admin" напиши, что именно непонятно.
4. Ты должен говорить вежливо, человеческим языком, без канцелярита.
5. Не обещай того, чего бот не может сделать сам (например, не подтверждай окончательно запись,
   если в будущем логика будет требовать проверки человеком).

ФОРМАТ ОТВЕТА – ВСЕГДА ЧИСТЫЙ JSON БЕЗ ОБЪЯСНЕНИЙ ВНЕ JSON:

{
  "action": "reply_only" | "need_human",
  "answer": "текст для клиента",
  "comment_for_admin": "опционально, комментарий для администратора"
}

Никакого другого текста вне JSON быть не должно.
"""


def build_user_prompt(context: Dict[str, Any]) -> str:
    """
    Собираем текст, который пойдёт в роль user для модели.
    Здесь можно расширять контекст (история посещений, тип клиента и т.п.).
    """
    user_text: str = context.get("user_text", "")
    is_known_client: bool = bool(context.get("is_known_client", False))
    visit_summary: str = context.get("visit_summary") or ""

    parts: list[str] = []

    parts.append(f"Наш клиент: {is_known_client}")
    if visit_summary:
        parts.append(f"Краткая история посещений:\n{visit_summary}")

    parts.append("\nСообщение клиента:")
    parts.append(user_text)

    return "\n\n".join(parts)


def call_chat_model(context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Вызов ChatGPT через OpenAI v1 API.
    Возвращает dict с полями:
        action, answer, comment_for_admin
    """
    user_prompt = build_user_prompt(context)

    response = client_ai.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.choices[0].message.content or ""

    # Модель обязана вернуть JSON — пробуем его распарсить.
    try:
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("JSON не является объектом")
    except Exception:
        # Любая проблема – переводим в режим need_human.
        return {
            "action": "need_human",
            "answer": (
                "Спасибо за сообщение. Сейчас подключу администратора, "
                "чтобы он дал точный ответ."
            ),
            "comment_for_admin": "Модель вернула невалидный JSON или произошла ошибка парсинга.",
        }

    # Безопасно вытаскиваем поля
    action = data.get("action") or "reply_only"
    answer = data.get("answer") or (
        "Спасибо за сообщение. Сейчас подключу администратора,"
        " чтобы он ответил более подробно."
    )
    comment = data.get("comment_for_admin") or ""

    return {
        "action": str(action),
        "answer": str(answer),
        "comment_for_admin": str(comment),
    }


def process_message(
    msg: Dict[str, Any],
    wa_client: Any,
    yc_client: Optional[Any] = None,
    state: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Главная функция "мозга", которую вызывает bot_loop.

    Параметры:
        msg: {
            "text": str,
            "channel_uuid": str,
            "user_id": int | str,
            "phone": str | None,
            ... (можно расширять)
        }
        wa_client: экземпляр WahelpClient (у него есть send_message)
        yc_client: в будущем – клиент YCLIENTS (сейчас None)
        state: любое доп. состояние (позже можно подключить)

    Возвращает:
        dict с тем, что вернул wa_client.send_message(...) ИЛИ
        {"skipped": True} если решили не отвечать.
    """

    text: str = msg.get("text") or ""
    channel_uuid: str = msg.get("channel_uuid") or ""
    user_id = msg.get("user_id")

    # На всякий случай: если нет канала или user_id — ничего не делаем
    if not channel_uuid or user_id is None:
        return {"skipped": True, "reason": "no_channel_or_user"}

    # --- Заглушки под YCLIENTS и историю клиента ---

    # Пока считаем, что клиент новый (потом заменим на запрос в YCLIENTS)
    is_known_client = False
    visit_summary = ""

    # Здесь в будущем:
    # if yc_client:
    #     ... запросить по телефону/ID историю посещений
    #     is_known_client = ...
    #     visit_summary = ...

    # --- Вызываем модель ---

    model_context: Dict[str, Any] = {
        "user_text": text,
        "is_known_client": is_known_client,
        "visit_summary": visit_summary,
    }

    model_result = call_chat_model(model_context)

    action = model_result.get("action", "reply_only")
    answer_text = model_result.get("answer", "")
    admin_comment = model_result.get("comment_for_admin", "")

    # --- Логика действий ---

    # Если модель сказала "ответить клиенту"
    resp_api: Optional[Dict[str, Any]] = None
    if answer_text.strip():
        resp_api = wa_client.send_message(
            channel_uuid=channel_uuid,
            user_id=user_id,
            text=answer_text,
        )

    # Если нужен человек — можно дополнительно отправить уведомление админу
    # (на данный момент просто логируем через comment_for_admin — ты увидишь это в логах).
    if action == "need_human" and admin_comment:
        print("\n[ASSISTANT] Нужен администратор. Комментарий:")
        print(admin_comment)

    return {
        "action": action,
        "answer": answer_text,
        "comment_for_admin": admin_comment,
        "api_response": resp_api,
    }