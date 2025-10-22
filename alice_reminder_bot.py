import os
import re
import sqlite3
import requests
import dateparser
from datetime import datetime
from flask import Flask, request
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = int(os.environ.get("CHAT_ID"))
THREAD_ID = os.environ.get("THREAD_ID")
THREAD_ID = int(THREAD_ID) if THREAD_ID and THREAD_ID.isdigit() else None
DATABASE_URL = "sqlite:///reminders.db"

# === НАСТРОЙКА PLANER ===
jobstores = {"default": SQLAlchemyJobStore(url=DATABASE_URL)}
scheduler = BackgroundScheduler(jobstores=jobstores)
scheduler.start()

# === Flask сервер ===
app = Flask(__name__)

# --- Telegram utils ---
def send_to_telegram(text):
    """Отправка сообщения в Telegram (с поддержкой message_thread_id)"""
    data = {"chat_id": CHAT_ID, "text": text}
    if THREAD_ID:
        data["message_thread_id"] = THREAD_ID
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=data
    )

# --- SQLite utils ---
def db_connect():
    conn = sqlite3.connect("reminders.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT,
            remind_time TEXT
        )
    """)
    return conn

def add_task_to_db(text, remind_time):
    conn = db_connect()
    conn.execute("INSERT INTO reminders (text, remind_time) VALUES (?, ?)", (text, remind_time.isoformat()))
    conn.commit()
    conn.close()

def delete_task_from_db(task_id):
    conn = db_connect()
    conn.execute("DELETE FROM reminders WHERE id=?", (task_id,))
    conn.commit()
    conn.close()

def get_all_tasks():
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT id, text, remind_time FROM reminders ORDER BY remind_time ASC")
    tasks = cur.fetchall()
    conn.close()
    return tasks

# --- Планировщик ---
def schedule_reminder(text, remind_time):
    scheduler.add_job(
        send_to_telegram,
        "date",
        run_date=remind_time,
        args=[f"🔔 Напоминание: {text}"],
        id=f"{text}_{remind_time.timestamp()}",
        replace_existing=False
    )
    add_task_to_db(text, remind_time)

# --- Разбор даты и текста ---
def extract_time_and_text(command: str):
    """Извлекает дату и текст задачи из фразы."""
    task_text = re.sub(r"^напомни( мне)?", "", command).strip()
    parsed_time = dateparser.parse(
        task_text,
        languages=["ru"],
        settings={"PREFER_DATES_FROM": "future"}
    )
    return task_text, parsed_time

# --- Алиса обработчик ---
@app.route("/alice", methods=["POST"])
def handle_alice():
    data = request.json
    command = data["request"]["command"].lower().strip()
    task_text, remind_time = extract_time_and_text(command)

    if not remind_time:
        return alice_response("Не поняла, когда нужно напомнить. Повтори время, пожалуйста.", end_session=False)

    cleaned_text = re.sub(r"\b(сегодня|завтра|через|в|через|дня|час[ауе]?)\b.*", "", task_text).strip()
    if not cleaned_text:
        cleaned_text = task_text

    schedule_reminder(cleaned_text, remind_time)
    send_to_telegram(f"✅ Создано напоминание: «{cleaned_text}» на {remind_time.strftime('%d.%m %H:%M')}")
    return alice_response(f"Хорошо, я напомню {cleaned_text} {remind_time.strftime('%d.%m в %H:%M')}")

def alice_response(text, end_session=True):
    return {"response": {"text": text, "end_session": end_session}, "version": "1.0"}

# --- Telegram обработчик ---
@app.route(f"/bot/{TELEGRAM_TOKEN}", methods=["POST"])
def handle_telegram():
    data = request.json
    message = data.get("message", {})
    text = message.get("text", "")
    chat_id = message["chat"]["id"]

    if chat_id != CHAT_ID:
        return "ignored"

    if text.startswith("/start"):
        send_menu(chat_id)
    elif text.startswith("/menu"):
        send_menu(chat_id)
    elif text.startswith("/list"):
        show_tasks()
    elif text.startswith("/delete"):
        delete_task_command(text)
    elif text.startswith("/status"):
        send_to_telegram("✅ Планировщик активен. Все задачи выполняются.")
    elif text.startswith("/add"):
        send_to_telegram("🗓 Напиши фразу, например:\n/add позвонить маме завтра в 9 утра")
    elif text.startswith("/"):
        send_to_telegram("Неизвестная команда. Используй /menu.")
    else:
        add_task_via_text(text)

    return "ok"

# --- Telegram подфункции ---
def send_menu(chat_id):
    menu = (
        "📖 Меню напоминаний:\n"
        "/add – добавить напоминание\n"
        "/list – показать список\n"
        "/delete [id] – удалить напоминание\n"
        "/status – проверить состояние\n"
        "/menu – показать меню"
    )
    data = {"chat_id": chat_id, "text": menu}
    if THREAD_ID:
        data["message_thread_id"] = THREAD_ID
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data=data)

def show_tasks():
    tasks = get_all_tasks()
    if not tasks:
        send_to_telegram("📭 У тебя нет активных напоминаний.")
    else:
        msg = "📋 Список напоминаний:\n\n"
        for tid, ttext, ttime in tasks:
            dt = datetime.fromisoformat(ttime)
            msg += f"{tid}. {ttext} — {dt.strftime('%d.%m %H:%M')}\n"
        send_to_telegram(msg)

def delete_task_command(text):
    parts = text.split()
    if len(parts) < 2:
        send_to_telegram("❌ Укажи номер задачи: /delete 3")
    else:
        try:
            task_id = int(parts[1])
            delete_task_from_db(task_id)
            send_to_telegram(f"🗑 Напоминание {task_id} удалено.")
        except Exception:
            send_to_telegram("⚠️ Неверный ID задачи.")

def add_task_via_text(text):
    if text.lower().startswith(("добавь", "напомни", "/add")):
        task_text, remind_time = extract_time_and_text(text)
        if not remind_time:
            send_to_telegram("⚠️ Не смог определить время. Пример: /add купить хлеб завтра в 10.")
            return
        cleaned_text = re.sub(r"\b(сегодня|завтра|через|в|через|дня|час[ауе]?)\b.*", "", task_text).strip()
        if not cleaned_text:
            cleaned_text = task_text
        schedule_reminder(cleaned_text, remind_time)
        send_to_telegram(f"✅ Напоминание добавлено: «{cleaned_text}» на {remind_time.strftime('%d.%m %H:%M')}")
    else:
        send_to_telegram("Используй /menu для списка команд.")

@app.route("/")
def index():
    return "🤖 Reminder бот и навык Алисы активны!"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

