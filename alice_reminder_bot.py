import os
import re
import json
from datetime import datetime, timedelta
import dateparser
import telebot
from flask import Flask, request, jsonify

# === Конфигурация ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")  # твой chat_id
MESSAGE_THREAD_ID = os.getenv("MESSAGE_THREAD_ID")  # id ветки
bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)


# === Расширенный парсер времени ===
def extract_time_and_text(command: str, request_json=None):
    """Извлекает текст задачи и время напоминания (включая обработку YANDEX.NLU)."""
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

        # "через 1 минуту" или подобные конструкции
        if number and "через" in command:
            parsed_time = datetime.now() + timedelta(minutes=int(number))
        elif relative_days or relative_hours or relative_minutes:
            parsed_time = datetime.now() + timedelta(
                days=relative_days, hours=relative_hours, minutes=relative_minutes
            )

    # fallback: если NLU не помогло, используем dateparser
    if not parsed_time:
        parsed_time = dateparser.parse(
            task_text,
            languages=["ru"],
            settings={"PREFER_DATES_FROM": "future"}
        )

    return task_text, parsed_time


# === Маршрут для Яндекс.Диалогов ===
@app.route("/alice", methods=["POST"])
def alice_webhook():
    data = request.json
    command = data.get("request", {}).get("original_utterance", "").lower().strip()

    # Пустой запрос — приветствие
    if not command:
        return jsonify({
            "version": "1.0",
            "response": {
                "text": "Привет! Я помогу тебе поставить напоминание. Например: «напомни купить хлеб через 10 минут».",
                "end_session": False
            }
        })

    # Обрабатываем напоминание
    task_text, remind_time = extract_time_and_text(command, data)

    if not remind_time:
        return jsonify({
            "version": "1.0",
            "response": {
                "text": "Не поняла, когда нужно напомнить. Повтори время, пожалуйста.",
                "end_session": False
            }
        })

    # Форматируем вывод
    remind_time_str = remind_time.strftime("%H:%M:%S %d.%m.%Y")

    # Отправляем в Telegram
    message = f"⏰ Напоминание: {task_text}\n🕒 Время: {remind_time_str}"
    try:
        bot.send_message(CHAT_ID, message, message_thread_id=MESSAGE_THREAD_ID)
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")

    # Ответ пользователю
    return jsonify({
        "version": "1.0",
        "response": {
            "text": f"Хорошо, напомню {task_text} в {remind_time.strftime('%H:%M')}.",
            "end_session": False
        }
    })


# === Проверка сервера ===
@app.route("/", methods=["GET"])
def index():
    return "✅ Reminder bot is running!"


# === Запуск ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

