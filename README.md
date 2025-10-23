🤖 Reminder Bot для Алисы + Telegram

> Голосовой помощник, который принимает задачи через **Яндекс.Алису**, анализирует текст с помощью NLU и отправляет напоминания в **Telegram**.

🧠 Что делает проект

1. Пользователь говорит Алисе:  
   > «Алиса, напомни купить хлеб через 10 минут»

2. Алиса через Webhook отправляет запрос на сервер.

3. Сервер (Flask + Python):
```
   - извлекает задачу и время (`YANDEX.DATETIME`, `YANDEX.NUMBER`);
   - формирует напоминание;
   - пересылает его в Telegram-бота.
```

4. Telegram-бот пишет сообщение в нужный чат или ветку:
```
⏰ Напоминание: купить хлеб
🕒 Время: 14:35:00 22.10.2025
```


⚙️ Технологии
```
- **Python 3.10+**
- **Flask** — приём Webhook-запросов от Яндекса  
- **PyTelegramBotAPI (telebot)** — отправка сообщений в Telegram  
- **dateparser** — гибкий парсинг времени  
- **Render.com** — бесплатный хостинг с автозапуском Flask  
- **Яндекс.Диалоги** — голосовой интерфейс Алисы  
```


🚀 Быстрый старт

1. Клонируй репозиторий

```
git clone https://github.com/<your_username>/alice-telegram-reminder.git
cd alice-telegram-reminder
```
2. Установи зависимости
```
pip install -r requirements.txt
```
3. Настрой переменные окружения
Создай .env или задай в Render → Environment Variables:

```
TELEGRAM_TOKEN=твой_токен_бота
CHAT_ID=твой_chat_id
MESSAGE_THREAD_ID=твой_message_thread_id
(CHAT_ID — ID пользователя или группы, MESSAGE_THREAD_ID — если бот пишет в ветку)
```
🌐 Настройка в Render
Создай новый проект → Web Service

Репозиторий: GitHub

Укажи:
```
Build Command: pip install -r requirements.txt

Start Command: python main.py

Port: 8080
```
После деплоя Render выдаст URL, например:
```
https://reminder-bot.onrender.com
```

🗣️ Настройка Яндекс.Диалога
Перейди в Яндекс.Диалоги → Навыки

Создай навык типа "Навык с webhook"

В поле Webhook URL укажи:

```
https://reminder-bot.onrender.com/alice
```
Сохрани и нажми «Проверить URL»
✅ должен появиться ответ 200 OK

🧩 Пример запроса и ответа
Запрос (от Алисы):

```
{
  "request": {
    "original_utterance": "напомни купить хлеб через 1 минуту",
    "nlu": {
      "tokens": ["напомни", "купить", "хлеб", "через", "1", "минуту"],
      "entities": [
        {"type": "YANDEX.NUMBER", "value": 1}
      ]
    }
  }
}
```
Ответ (сервер → Алисе):

```
{
  "response": {
    "text": "Хорошо, напомню купить хлеб в 14:35.",
    "end_session": false
  },
  "version": "1.0"
}
```
Сообщение в Telegram:

```
⏰ Напоминание: купить хлеб
🕒 Время: 14:35:00 22.10.2025
📁 Структура проекта
```
```
📦 alice-telegram-reminder
├── main.py                # основной сервер Flask
├── requirements.txt       # зависимости
├── README.md              # документация (этот файл)
└── .env.example           # пример переменных окружения
```
🧩 Пример .env.example
```
TELEGRAM_TOKEN=1234567890:ABCDEF-your-telegram-token
CHAT_ID=987654321
MESSAGE_THREAD_ID=1234
PORT=8080
```
```
🛠 Возможности
✅ Создание напоминаний по голосу
✅ Гибкий парсинг фраз на русском
✅ Поддержка слов «через», «завтра», «в 10 утра» и т.п.
✅ Отправка в Telegram (в чат или ветку)
✅ Хостинг на бесплатной платформе Render
✅ Поддержка интерфейса кнопок и будущего расширения меню
```
📜 Лицензия
MIT License — свободно используйте и дорабатывайте проект.
