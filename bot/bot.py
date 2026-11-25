#!/usr/bin/env python3
"""Small, stateless Telegram practice bot using only the Python standard library."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


SKILLS_URL = "https://github.com/FokinArts/speaker-ai-meetup"
WORKFLOW_URL = "https://github.com/FokinArts/speaker-ai-meetup/blob/main/docs/meetup-speaker-ai/toolkit/workflow.md"
ROOM_SKILL_URL = "https://github.com/FokinArts/speaker-ai-meetup/tree/main/docs/meetup-speaker-ai/toolkit/skills/rehearse-the-room"
CLAIM = "«Мы внедрили ИИ в разработку и повысили качество»"
INTRO = (
    "Учебная заявка:\n"
    f"{CLAIM}\n\n"
    "За 45 секунд проверьте, хватает ли в ней фактов. Выберите вопрос — "
    "это самостоятельная практика, ответы и голоса не собираются."
)
ANSWERS = {
    "percent": (
        "«На сколько процентов?»\n\n"
        "Пока это неизвестно: в заявке нет числа и способа его получить. "
        "Назовите метрику, исходный уровень и период сравнения. Уточните, "
        "что именно значит «качество», сколько задач вошло в выборку и "
        "как учитывались ошибки. Не подставляйте процент без измерений."
    ),
    "task": (
        "«Какую задачу проверим?»\n\n"
        "Выберите один повторяемый сценарий разработки и сравните его «до/после» "
        "на сопоставимых задачах. Заранее определите критерии качества "
        "(например, дефекты на проверке и доля принятых изменений), кто их "
        "оценивает и за какой период. Один удачный пример ещё не доказывает "
        "общий эффект."
    ),
    "model": (
        "«Какую модель взяли?»\n\n"
        "Одного названия модели недостаточно, чтобы подтвердить результат. "
        "Укажите модель и версию на момент проверки, где она запускалась, "
        "какие данные ей давали и почему выбрали её. Добавьте ограничения "
        "по приватности, стоимости и проверке человеком. Если точная версия "
        "не зафиксирована — так и скажите."
    ),
}
ROOM_INTRO = (
    "«Дебаг заклинаний» — репетиция роли\n\n"
    "Совет: «Делегируйте отчёт». Ваша роль: «На финальном документе должна стоять моя подпись».\n\n"
    "Сначала подумайте сами: сформулируйте одно действие на завтра, которое делегирует подготовку, "
    "но сохраняет ваше ограничение. Не отправляйте ответ боту — просто обдумайте его и нажмите кнопку сверки."
)
ROOM_ANSWER = (
    "Сверка варианта\n\n"
    "Первый вопрос — включает ли «отчёт» финальную проверку и подпись. Точная цитата: «Делегируйте отчёт».\n\n"
    "Черновик: попросить коллегу собрать отчёт по согласованному плану.\n"
    "Проверка: самому проверить итоговый документ.\n"
    "Подпись: оставить её за собой.\n\n"
    "Например: «Завтра попрошу коллегу собрать черновик отчёта, сам проверю итоговый документ и подпишу финальную версию». "
    "Сравните со своим вариантом: есть ли конкретное действие на завтра и сохранены ли проверка и подпись? "
    "Это пример по вымышленному условию, не свидетельство ответов реальных слушателей."
)

BUTTONS = [
    [{"text": "На сколько процентов?", "callback_data": "percent"}],
    [{"text": "Какую задачу проверим?", "callback_data": "task"}],
    [{"text": "Какую модель взяли?", "callback_data": "model"}],
    [{"text": "Открыть «Дебаг заклинаний»", "callback_data": "room_start"}],
    [{"text": "↻ Повторить", "callback_data": "restart"}],
    [{"text": "Скачать навыки", "url": SKILLS_URL}],
]
ROOM_BUTTONS = [
    [{"text": "Сверить мой вариант", "callback_data": "room_review"}],
    [{"text": "Сначала", "callback_data": "room_restart"}],
    [{"text": "Рабочая карточка", "url": WORKFLOW_URL}],
    [{"text": "Навык репетиции зала", "url": ROOM_SKILL_URL}],
    [{"text": "Кейс ПК", "callback_data": "legacy_start"}],
]


class TelegramError(Exception):
    """Sanitized Telegram/network error; never includes request URL or body."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def permanent(self) -> bool:
        return self.status_code in (400, 403)


class TelegramClient:
    def __init__(self, token: str, timeout: int = 35) -> None:
        self._base = f"https://api.telegram.org/bot{token}/"
        self._timeout = timeout

    def call(self, method: str, payload: dict[str, Any]) -> Any:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._base + method,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Telegram's response body and URL can contain sensitive details; omit both.
            raise TelegramError(f"HTTP {exc.code}", status_code=exc.code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise TelegramError("network error") from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise TelegramError("invalid API response") from None

        if not isinstance(result, dict) or not result.get("ok"):
            error_code = result.get("error_code") if isinstance(result, dict) else None
            status_code = error_code if isinstance(error_code, int) else None
            suffix = f" (API {status_code})" if status_code is not None else ""
            raise TelegramError("Telegram API rejected request" + suffix, status_code=status_code)
        return result.get("result")

    def get_updates(self, offset: int | None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": 25, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        result = self.call("getUpdates", payload)
        return result if isinstance(result, list) else []


def keyboard() -> dict[str, Any]:
    return {"inline_keyboard": BUTTONS}


def room_keyboard() -> dict[str, Any]:
    return {"inline_keyboard": ROOM_BUTTONS}


def send_intro(api: TelegramClient, chat_id: int, room: bool = False) -> None:
    api.call("sendMessage", {
        "chat_id": chat_id,
        "text": ROOM_INTRO if room else INTRO,
        "reply_markup": room_keyboard() if room else keyboard(),
        "disable_web_page_preview": True,
    })


def handle_update(api: TelegramClient, update: dict[str, Any]) -> None:
    """Handle one update. IDs are used only transiently for Telegram API replies."""
    message = update.get("message")
    if isinstance(message, dict):
        text = message.get("text")
        chat = message.get("chat")
        command = text.split(maxsplit=1)[0].split("@", 1)[0] if isinstance(text, str) and text.split() else ""
        if command == "/start":
            if isinstance(chat, dict) and isinstance(chat.get("id"), int):
                args = text.split(maxsplit=1)
                room = len(args) > 1 and args[1].strip().lower() == "room"
                send_intro(api, chat["id"], room=room)
        return

    query = update.get("callback_query")
    if not isinstance(query, dict):
        return
    query_id = query.get("id")
    data = query.get("data")
    message = query.get("message")
    chat = message.get("chat") if isinstance(message, dict) else None
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    message_id = message.get("message_id") if isinstance(message, dict) else None

    if not isinstance(query_id, str):
        return
    # Always attempt acknowledgement; a duplicate/expired callback is harmless.
    try:
        api.call("answerCallbackQuery", {"callback_query_id": query_id})
    except TelegramError as exc:
        # Expired/duplicate callback acknowledgements are common on redelivery.
        # Transient errors and 403 must reach the poller for retry/skip handling.
        if not (exc.status_code == 400):
            raise

    if data in ("restart", "room_start", "legacy_start", "room_restart"):
        if isinstance(chat_id, int) and isinstance(message_id, int):
            room = data in ("room_start", "room_restart")
            api.call("editMessageText", {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": ROOM_INTRO if room else INTRO,
                "reply_markup": room_keyboard() if room else keyboard(),
                "disable_web_page_preview": True,
            })
        return

    if data == "room_review":
        if isinstance(chat_id, int) and isinstance(message_id, int):
            api.call("editMessageText", {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": ROOM_ANSWER + "\n\nСверить ещё раз или перейти к кейсу ПК?",
                "reply_markup": room_keyboard(),
                "disable_web_page_preview": True,
            })
        return

    answer = ANSWERS.get(data) if isinstance(data, str) else None
    if answer and isinstance(chat_id, int) and isinstance(message_id, int):
        api.call("editMessageText", {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": answer + "\n\nВыберите следующий вопрос или нажмите «Повторить».",
            "reply_markup": keyboard(),
            "disable_web_page_preview": True,
        })


def load_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    token_file = os.environ.get("TELEGRAM_BOT_TOKEN_FILE", "").strip()
    if token and token_file:
        raise RuntimeError("Set only one token source: TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN_FILE")
    if token_file:
        path = Path(token_file)
        if path.stat().st_mode & 0o077:
            raise RuntimeError("Token file permissions must be owner-only (for example chmod 600)")
        token = path.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN_FILE")
    return token


def run(api: TelegramClient) -> None:
    offset: int | None = None  # In-memory Telegram cursor only; never persisted.
    backoff = 1
    while True:
        try:
            updates = api.get_updates(offset)
            retry_update = False
            for update in updates:
                update_id = update.get("update_id")
                try:
                    handle_update(api, update)
                except TelegramError as exc:
                    # Do not log update/chat/user IDs, payloads, bodies, token, or URLs.
                    if exc.permanent:
                        print(
                            f"Update skipped after permanent Telegram error ({exc.status_code})",
                            file=sys.stderr,
                            flush=True,
                        )
                    else:
                        print(f"Update handling failed: {exc}; retrying", file=sys.stderr, flush=True)
                        retry_update = True
                        break  # Leave transiently failed update unacknowledged for retry.
                if isinstance(update_id, int):
                    offset = update_id + 1
            if retry_update:
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
            else:
                backoff = 1
        except TelegramError as exc:
            if exc.permanent:
                print(
                    f"Polling stopped after permanent Telegram error ({exc.status_code})",
                    file=sys.stderr,
                    flush=True,
                )
                return
            print(f"Polling failed: {exc}; retrying in {backoff}s", file=sys.stderr, flush=True)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)
        except KeyboardInterrupt:
            print("Stopped.", file=sys.stderr, flush=True)
            return


def main() -> int:
    try:
        run(TelegramClient(load_token()))
    except (RuntimeError, OSError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
