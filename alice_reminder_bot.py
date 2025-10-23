import os
import re
from datetime import datetime, timedelta
import dateparser
import pytz
import telebot
from flask import Flask, request, jsonify

# === Конфигурация ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MESSAGE_THREAD_ID = os.getenv("MESSAGE_THREAD_ID")  # можно оставить пустым
MSK = pytz.timezone("Europe/Moscow")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# === Парсинг даты ===
def extract_time_and_text(command: str, request_json=None):
    task_text = re.sub(r"^напомни( мне)?", "", command, flags=re.IGNORECASE).strip()
    parsed_time = None

    if request_json:
        entities = request_json.get("request", {}).get("nlu", {}).get("entities", [])
        number = None
        relative_days = 0
        relative_hours = 0
        relative_minutes = 0

        for e in entities:
            if e["type"] == "YANDEX.NUMBER":
                number = e["value"]
            elif e["type"] == "YANDEX.DATETIME":
                val = e["value"]
                if val.get("day_is_relative"):
                    relative_days = val.get("day", 0)
                if val.get("hour_is_relative"):
                    relative_hours = val.get("hour", 0)
                if val.get("minute_is_relative"):
                    relative_minutes = val.get("minute", 0)

        if number and "через" in command:
            parsed_time = datetime.now(MSK) + timedelta(minutes=int(number))
        elif relative_days or relative_hours or relative_minutes:
            parsed_time = datetime.now(MSK) + timedelta(
                days=relative_days, hours=relative_hours, minutes=relative_minutes
            )

    if not parsed_time:
        parsed_time = dateparser.parse(
            task_text,
            languages=["ru"],
            settings={"PREFER_DATES_FROM": "future", "TIMEZONE": "Europe/Moscow"}
        )

    return task_text, parsed_time


# === Webhook Алисы ===
@app.route("/alice", methods=["POST"])
def alice_webhook():
    data = request.json
    command = data.get("request", {}).get("original_utterance", "").lower().strip()

    if not command:
        return jsonify({
            "version": "1.0",
            "response": {
                "text": "Привет! Я помогу поставить напоминание. Например: «напомни позвонить маме через 5 минут».",
                "end_session": False
            }
        })

    task_text, remind_time = extract_time_and_text(command, data)

    if not remind_time:
        return jsonify({
            "version": "1.0",
            "response": {
                "text": "Не поняла, когда нужно напомнить. Повтори время, пожалуйста.",
                "end_session": False
            }
        })

    remind_time_str = remind_time.strftime("%H:%M:%S %d.%m.%Y")
    message = f"⏰ Напоминание: {task_text}\n🕒 Время: {remind_time_str}"

    print(f"Отправка в Telegram: {message}")

    try:
        if MESSAGE_THREAD_ID:
            bot.send_message(CHAT_ID, message, message_thread_id=MESSAGE_THREAD_ID)
        else:
            bot.send_message(CHAT_ID, message)
        print("✅ Сообщение отправлено в Telegram")
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")

    return jsonify({
        "version": "1.0",
        "response": {
            "text": f"Хорошо, напомню {task_text} в {remind_time.strftime('%H:%M')}.",
            "end_session": False
        }
    })


@app.route("/", methods=["GET"])
def index():
    return "✅ Reminder bot is running! (Moscow time)"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

