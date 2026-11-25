#!/usr/bin/env python3
"""Offline smoke test using a tiny Telegram API test double."""

import bot


class FakeTelegram:
    def __init__(self):
        self.calls = []

    def call(self, method, payload):
        self.calls.append((method, payload))
        return True


class DuplicateButtonTelegram(FakeTelegram):
    def __init__(self):
        super().__init__()
        self.edit_count = 0
        self.offsets = []
        self.poll_count = 0

    def call(self, method, payload):
        self.calls.append((method, payload))
        if method == "editMessageText":
            self.edit_count += 1
            if self.edit_count == 2:
                # Simulates Telegram's 400 "message is not modified" response.
                raise bot.TelegramError("Telegram API rejected request (API 400)", status_code=400)
        return True

    def get_updates(self, offset):
        self.offsets.append(offset)
        self.poll_count += 1
        if self.poll_count == 1:
            click = lambda update_id: {
                "update_id": update_id,
                "callback_query": {
                    "id": f"temporary-{update_id}",
                    "data": "percent",
                    "message": {"message_id": 7, "chat": {"id": 42}},
                },
            }
            return [
                click(10),
                click(11),  # Duplicate click: edit is unchanged, Telegram returns 400.
                {"update_id": 12, "message": {"text": "/start", "chat": {"id": 42}}},
            ]
        raise KeyboardInterrupt


def main():
    api = FakeTelegram()

    bot.handle_update(api, {
        "update_id": 1,
        "message": {"text": "/start meetup", "chat": {"id": 42}},
    })
    method, payload = api.calls[-1]
    assert method == "sendMessage"
    assert payload["chat_id"] == 42
    assert "Мы внедрили ИИ в разработку и повысили качество" in payload["text"]
    buttons = payload["reply_markup"]["inline_keyboard"]
    assert [row[0]["text"] for row in buttons[:3]] == [
        "На сколько процентов?", "Какую задачу проверим?", "Какую модель взяли?"
    ]
    assert buttons[-2][0]["callback_data"] == "restart"
    assert buttons[-1][0]["url"] == bot.SKILLS_URL
    assert any(row[0].get("callback_data") == "room_start" for row in buttons)

    bot.handle_update(api, {
        "update_id": 10,
        "message": {"text": "/start room", "chat": {"id": 42}},
    })
    room_payload = api.calls[-1][1]
    assert room_payload["text"] == bot.ROOM_INTRO
    assert "Сначала подумайте сами" in room_payload["text"]
    room_buttons = room_payload["reply_markup"]["inline_keyboard"]
    assert room_buttons[0][0] == {"text": "Сверить мой вариант", "callback_data": "room_review"}
    assert room_buttons[1][0]["callback_data"] == "room_restart"
    assert room_buttons[2][0]["url"] == bot.WORKFLOW_URL
    assert room_buttons[3][0]["url"] == bot.ROOM_SKILL_URL

    bot.handle_update(api, {
        "update_id": 11,
        "callback_query": {
            "id": "room-review-query",
            "data": "room_review",
            "message": {"message_id": 8, "chat": {"id": 42}},
        },
    })
    room_answer = api.calls[-1][1]
    assert "Черновик:" in room_answer["text"]
    assert "Проверка:" in room_answer["text"]
    assert "Подпись:" in room_answer["text"]

    bot.handle_update(api, {
        "update_id": 12,
        "callback_query": {
            "id": "room-restart-query",
            "data": "room_restart",
            "message": {"message_id": 8, "chat": {"id": 42}},
        },
    })
    assert api.calls[-1][1]["text"] == bot.ROOM_INTRO

    bot.handle_update(api, {
        "update_id": 2,
        "callback_query": {
            "id": "ephemeral-query",
            "data": "percent",
            "message": {"message_id": 7, "chat": {"id": 42}},
        },
    })
    assert [call[0] for call in api.calls[-2:]] == ["answerCallbackQuery", "editMessageText"]
    assert "исходный уровень" in api.calls[-1][1]["text"]
    assert all("storage" not in call[1] for call in api.calls)

    bot.handle_update(api, {
        "update_id": 3,
        "callback_query": {
            "id": "ephemeral-query-2",
            "data": "restart",
            "message": {"message_id": 7, "chat": {"id": 42}},
        },
    })
    assert api.calls[-1][0] == "editMessageText"
    assert api.calls[-1][1]["text"] == bot.INTRO

    # The duplicate button update gets a permanent 400, but the following
    # update is still handled and the next poll cursor advances beyond it.
    polling_api = DuplicateButtonTelegram()
    bot.run(polling_api)
    assert polling_api.edit_count == 2
    assert any(method == "sendMessage" for method, _ in polling_api.calls)
    assert polling_api.offsets == [None, 13]

    print("OK: legacy and room flows, review, restart, links, duplicate click, and permanent-error queue progress")


if __name__ == "__main__":
    main()
