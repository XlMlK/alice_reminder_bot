# alice_reminder_bot.py
import os
import logging
from datetime import datetime, timedelta
import pytz
import dateparser
import json
import re

from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from telebot import TeleBot, types

import storage

# ---- Конфигурация (через ENV) ----
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
# Если TELEGRAM_CHAT_ID не задан, бот будет реагировать на любого, кто напишет ему в Telegram
CHAT_ID = os.getenv("CHAT_ID")  # опционально
THREAD_ID = os.getenv("THREAD_ID")  # опционально
SQLITE_JOBSTORE_DB = os.getenv("SQLITE_JOBSTORE_DB", "sqlite:///reminders.db")  # APScheduler jobstore URL

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN must be set as environment variable")

# ---- Логи ----
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("reminder")

# ---- Часовые пояса ----
MSK = pytz.timezone("Europe/Moscow")
UTC = pytz.utc

# ---- Flask + Bot + Scheduler ----
app = Flask(__name__)

# ---- Health check endpoint ----
@app.route("/health", methods=["GET"])
def health_check():
    """Endpoint для UptimeRobot и проверки работоспособности"""
    return jsonify({"status": "ok"}), 200

# ---- Telegram Bot ----
bot = TeleBot(TELEGRAM_TOKEN)  

# ---- Scheduler ----
jobstores = {"default": SQLAlchemyJobStore(url=SQLITE_JOBSTORE_DB)}
scheduler = BackgroundScheduler(jobstores=jobstores)
scheduler.start()

# ---- Утилиты ----
def parse_time(input_text: str, yandex_request: dict = None):
    """
    Распознаёт время из текста на русском.
    Поддерживает: "через 10 минут", "завтра в 12:00", "в 18:30", "через 2 часа".
    Возвращает datetime в UTC.
    """
    import re
    input_text = (input_text or "").strip()
    parsed_dt = None

    # 1️⃣ Пытаемся распознать через dateparser
    dp = dateparser.parse(
        input_text,
        languages=["ru"],
        settings={
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": True,
            "TIMEZONE": "Europe/Moscow"
        }
    )
    if dp:
        parsed_dt = dp if dp.tzinfo else MSK.localize(dp)

    # 2️⃣ Ручной парсинг "через N минут/часов"
    if not parsed_dt:
        m = re.search(r'через\s+(\d+)\s*(минут|минуты|минута|час|часа|часов)', input_text.lower())
        if m:
            num = int(m.group(1))
            if 'час' in m.group(2):
                parsed_dt = datetime.now(MSK) + timedelta(hours=num)
            else:
                parsed_dt = datetime.now(MSK) + timedelta(minutes=num)

    if not parsed_dt:
        return None

    return parsed_dt.astimezone(UTC)

def clean_reminder_text(text: str) -> str:
    """
    Удаляет слова 'напомни', 'через', 'в', 'завтра' и т.п.
    Преобразует текст в более естественную форму.
    """
    text = text.lower().strip()
    text = re.sub(r'\b(напомни(ть)?|через|в|завтра|сегодня|пожалуйста)\b', '', text)
    text = re.sub(r'\s+', ' ', text).strip(' .,:;')
    return text.capitalize()

def schedule_job_and_store(alisa_user_id, chat_id, thread_id, text, remind_dt_utc):
    # store in DB
    iso = remind_dt_utc.isoformat()
    reminder_id = storage.add_reminder(alisa_user_id, str(chat_id), str(thread_id) if thread_id else None, text, iso)
    job_id = f"reminder_{reminder_id}"
    # schedule job in apscheduler
    scheduler.add_job(func=send_reminder_job, trigger='date', run_date=remind_dt_utc, args=[reminder_id], id=job_id)
    storage.update_job_id(reminder_id, job_id)
    logger.info("Scheduled job %s for reminder %s at %s (UTC)", job_id, reminder_id, iso)
    return reminder_id

def send_reminder_job(reminder_id: int):
    """Функция, которую выполняет планировщик"""
    reminder = storage.get_by_id(reminder_id)
    if not reminder:
        logger.warning("Reminder %s not found (maybe deleted)", reminder_id)
        return
    chat_id = int(reminder["telegram_chat_id"])
    thread_id = reminder.get("telegram_thread_id")
    text = reminder["text"]
    remind_ts = reminder["remind_ts"]
    # human-friendly time in MSK for message
    dt = datetime.fromisoformat(remind_ts).astimezone(MSK)
    time_str = dt.strftime("%H:%M %d.%m.%Y (MSK)")
    msg = f"🔔 Напоминание: {text}\n🕒 {time_str}\n🆔 #{reminder_id}"
    try:
        if thread_id and thread_id != "None":
            bot.send_message(chat_id, msg, message_thread_id=int(thread_id))
        else:
            bot.send_message(chat_id, msg)
        logger.info("Sent reminder %s to chat %s", reminder_id, chat_id)
    except Exception as e:
        logger.exception("Failed to send reminder %s: %s", reminder_id, e)
    # optionally delete reminder after sending
    storage.delete_reminder(reminder_id)

# ---- Telegram command handlers (using Webhook processing in Flask route) ----
@bot.message_handler(commands=['start', 'help'])
def cmd_start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🗓 Список напоминаний", "➕ Добавить напоминание", "❌ Удалить напоминание")
    bot.send_message(
        message.chat.id,
        "Привет! 👋 Я бот-напоминалка.\n\n"
        "Можешь написать: «напомни купить хлеб через 10 минут»\n"
        "или выбрать действие кнопками ниже 👇",
        reply_markup=markup
    )
@bot.message_handler(func=lambda m: m.text == "🗓 Список напоминаний")
def button_list(message):
    cmd_list(message)

@bot.message_handler(commands=['list'])
def cmd_list(message):
    chat_id = str(message.chat.id)
    rows = [r for r in storage.get_all() if str(r["telegram_chat_id"]) == chat_id]

    if not rows:
        bot.send_message(message.chat.id, "📭 У тебя нет активных напоминаний.")
        return

    text = "📋 Твои напоминания:\n\n"
    for r in rows:
        dt = datetime.fromisoformat(r["remind_ts"]).astimezone(MSK)
        text += f"🔔 {r['id']}. {r['text']} — 🕒 {dt.strftime('%H:%M %d.%m.%Y')}\n"
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['delete'])
def cmd_delete(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "Использование: /delete <id>")
        return
    try:
        rid = int(parts[1])
        row = storage.get_by_id(rid)
        if not row:
            bot.send_message(message.chat.id, "Напоминание не найдено.")
            return
        # remove scheduled job if exists
        job_id = row.get("job_id")
        if job_id and scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
        storage.delete_reminder(rid)
        bot.send_message(message.chat.id, f"✅ Напоминание {rid} удалено.")
    except Exception as e:
        logger.exception("Error in delete cmd: %s", e)
        bot.send_message(message.chat.id, "Ошибка при удалении.")

@bot.message_handler(commands=['snooze'])
def cmd_snooze(message):
    parts = message.text.split()
    if len(parts) < 3:
        bot.send_message(message.chat.id, "Использование: /snooze <id> <minutes>")
        return
    try:
        rid = int(parts[1]); minutes = int(parts[2])
        row = storage.get_by_id(rid)
        if not row:
            bot.send_message(message.chat.id, "Напоминание не найдено.")
            return
        # compute new time
        old_dt = datetime.fromisoformat(row["remind_ts"]).astimezone(UTC)
        new_dt = old_dt + timedelta(minutes=minutes)
        # update DB: delete old, create new
        # For simplicity: delete old record and create new
        storage.delete_reminder(rid)
        new_id = storage.add_reminder(row.get("alisa_user_id"), row["telegram_chat_id"], row.get("telegram_thread_id"),
                                      row["text"], new_dt.isoformat())
        job_id = f"reminder_{new_id}"
        scheduler.add_job(func=send_reminder_job, trigger='date', run_date=new_dt, args=[new_id], id=job_id)
        storage.update_job_id(new_id, job_id)
        bot.send_message(message.chat.id, f"✅ Напоминание {rid} отложено на {minutes} минут (новый id {new_id}).")
    except Exception as e:
        logger.exception("Error snooze: %s", e)
        bot.send_message(message.chat.id, "Ошибка при отложении.")

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    """
    Если пользователь пишет свободный текст, пытаемся понять время и создать напоминание.
    """
    text = message.text.strip()
    parsed = parse_time(text, None)
    if not parsed:
        bot.reply_to(message, "Не понял время 😅 Попробуй: «напомни купить хлеб через 10 минут»")
        return

    clean_text = clean_reminder_text(text)
    reminder_id = schedule_job_and_store(
        alisa_user_id=None,
        chat_id=message.chat.id,
        thread_id=None,
        text=clean_text,
        remind_dt_utc=parsed
    )

    dt_local = parsed.astimezone(MSK)
    bot.reply_to(
        message,
        f"✅ Готово! Напомню: {clean_text.lower()} в {dt_local.strftime('%H:%M %d.%m.%Y')} (МСК)."
    )

# ---- Flask endpoints: Telegram webhook receiver and Yandex Alice ----
@app.route("/bot/" + TELEGRAM_TOKEN, methods=["POST"])
def telegram_webhook():
    """
    Telegram will POST updates here (setWebhook to https://your-url/bot/<token>)
    We pass updates to telebot for processing.
    """
    try:
        json_str = request.get_data().decode('utf-8')
        update = json.loads(json_str)
        bot.process_new_updates([types.Update.de_json(update)])
    except Exception as e:
        logger.exception("Error processing telegram update: %s", e)
    return "", 200

@app.route("/alice", methods=["POST"])
def alice_webhook():
    """
    Webhook from Yandex Alice.
    Example structure: request.original_utterance, request.nlu.entities
    """
    data = request.json or {}
    command = data.get("request", {}).get("original_utterance", "") or ""
    command = command.strip()
    # If empty -> greeting
    if not command:
        return jsonify({
            "version": "1.0",
            "response": {"text": "Привет! Скажи: напомни купить хлеб через 10 минут", "end_session": False}
        })

    parsed_dt = parse_time(command, data)
    if not parsed_dt:
        return jsonify({
            "version": "1.0",
            "response": {"text": "Не поняла, когда нужно напомнить. Повтори время, пожалуйста.", "end_session": False}
        })

    # determine where to send: either CHAT_ID (env) or map user -> chat (not implemented)
    target_chat = int(CHAT_ID) if CHAT_ID else None
    if not target_chat:
        # cannot send if no chat mapping - inform user
        logger.warning("No CHAT_ID configured; cannot send reminder to Telegram")
        return jsonify({
            "version": "1.0",
            "response": {"text": "Навык настроен, но не привязан Telegram-чат. Свяжи аккаунты.", "end_session": False}
        })

    # schedule and store
    reminder_id = schedule_job_and_store(alisa_user_id=None, chat_id=target_chat, thread_id=THREAD_ID, text=command, remind_dt_utc=parsed_dt)

    # reply to Alice
    local = parsed_dt.astimezone(MSK)
    text = f"Хорошо, напомню {command} в {local.strftime('%H:%M')}"
    return jsonify({"version": "1.0", "response": {"text": text, "end_session": False}})

# ---- Health check ----
#@app.route("/health", methods=["GET"])
#def health():
#    return jsonify({"status": "ok"}), 200

# ---- On startup: reschedule pending (APScheduler jobstore is persistent, but we ensure) ----
def reschedule_pending():
    rows = storage.get_pending()
    for r in rows:
        rid = r["id"]
        job_id = r.get("job_id") or f"reminder_{rid}"
        # if job exists - skip
        if scheduler.get_job(job_id):
            continue
        run_dt = datetime.fromisoformat(r["remind_ts"])
        try:
            scheduler.add_job(func=send_reminder_job, trigger='date', run_date=run_dt, args=[rid], id=job_id)
            storage.update_job_id(rid, job_id)
            logger.info("Rescheduled reminder %s at %s", rid, r["remind_ts"])
        except Exception:
            logger.exception("Failed to reschedule reminder %s", rid)

# run reschedule at startup
reschedule_pending()

# ---- Run (only for local dev) ----
if __name__ == "__main__":
    # For local dev: set webhook manually with bot.set_webhook()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
