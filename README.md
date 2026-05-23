# Sylph — Telegram Inline-бот с DeepSeek через AgentRouter

Inline Telegram-бот, который отвечает на вопросы с помощью DeepSeek v4 Pro через [AgentRouter](https://agentrouter.org).  
Пользователь вводит `@имя_бота запрос` в любом чате, получает ответ и публикует его одним нажатием.

## Возможности

- **Inline mode** — бот работает в любом чате без добавления
- **DeepSeek v4 Pro** через AgentRouter (OpenAI-совместимый API)
- **Retry + backoff** — автоматические повторы при ошибках и rate-limit
- **Anti-spam** — кулдаун между запросами одного пользователя
- **Защита от длинных запросов** — настраиваемый лимит символов
- **Graceful shutdown** — корректная остановка по SIGINT/SIGTERM
- **Логирование** — структурированные логи в stdout
- **Конфигурация через `.env`** — безопасное хранение токенов

## Структура проекта

```
Sylph/
├── main.py              # Точка входа, запуск бота
├── config/
│   ├── __init__.py
│   └── settings.py      # Загрузка и валидация настроек из .env
├── handlers/
│   ├── __init__.py
│   └── inline.py        # Обработчик inline-запросов
├── services/
│   ├── __init__.py
│   └── gemini.py        # LLM сервис (AgentRouter, retry, timeout)
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Быстрый старт

### 1. Создание Telegram-бота

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram.
2. Отправьте `/newbot`.
3. Введите имя бота (например, `Sylph Bot`).
4. Введите username бота (например, `sylph_gemini_bot`). Должен заканчиваться на `bot`.
5. Скопируйте полученный **токен** (`123456:ABC-DEF...`).

### 2. Включение Inline Mode

1. В том же чате с BotFather отправьте `/setinline`.
2. Выберите вашего бота.
3. Введите placeholder (например, `Задайте вопрос...`).
4. Готово — inline mode включён.

### 3. Получение AgentRouter API Key

1. Перейдите на [AgentRouter](https://agentrouter.org).
2. Зарегистрируйтесь и получите API ключ.
3. Скопируйте ключ.

### 4. Установка и запуск

```bash
# Клонировать репозиторий
git clone https://github.com/SpaZyyy/Sylph.git
cd Sylph

# Создать виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate

# Установить зависимости
pip install -r requirements.txt

# Настроить переменные окружения
cp .env.example .env
# Отредактируйте .env — замените <BotFather_Token> и <AgentRouter> на реальные ключи

# Запустить бота
python main.py
```

### 5. Тестирование Inline Mode

1. Откройте любой чат в Telegram.
2. Введите `@имя_вашего_бота какой-нибудь вопрос`.
3. Подождите 1–3 секунды — появится кнопка с ответом.
4. Нажмите на неё — ответ опубликуется в чат.

---

## Конфигурация

Все параметры задаются через `.env` (см. `.env.example`):

| Переменная | Описание | По умолчанию |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота от BotFather | *обязательно* |
| `AGENTROUTER_API_KEY` | API ключ AgentRouter | *обязательно* |
| `LLM_MODEL` | Модель LLM | `deepseek-v4-pro` |
| `MAX_QUERY_LENGTH` | Макс. длина запроса | `500` |
| `MAX_RESPONSE_LENGTH` | Макс. длина ответа | `4000` |
| `LLM_TIMEOUT` | Таймаут запроса к LLM (сек) | `60` |
| `LLM_MAX_RETRIES` | Макс. число повторов | `3` |
| `COOLDOWN_SECONDS` | Кулдаун между запросами | `3.0` |
| `INLINE_CACHE_TIME` | Кэш inline-ответа (сек) | `5` |
| `LOG_LEVEL` | Уровень логирования | `INFO` |

---

## Деплой на VPS / Linux

### Подготовка сервера

```bash
# Обновить систему
sudo apt update && sudo apt upgrade -y

# Установить Python
sudo apt install -y python3 python3-pip python3-venv git

# Клонировать и настроить
git clone https://github.com/SpaZyyy/Sylph.git
cd Sylph
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Настроить .env
cp .env.example .env
nano .env  # вставьте токены
```

### Запуск через systemd

Создайте файл сервиса:

```bash
sudo nano /etc/systemd/system/sylph-bot.service
```

Вставьте:

```ini
[Unit]
Description=Sylph Telegram Bot (DeepSeek via AgentRouter)
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/Sylph
ExecStart=/home/ubuntu/Sylph/.venv/bin/python main.py
Restart=on-failure
RestartSec=10
EnvironmentFile=/home/ubuntu/Sylph/.env

[Install]
WantedBy=multi-user.target
```

Активируйте сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl enable sylph-bot
sudo systemctl start sylph-bot

# Проверить статус
sudo systemctl status sylph-bot

# Посмотреть логи
sudo journalctl -u sylph-bot -f
```

### Управление сервисом

```bash
sudo systemctl stop sylph-bot      # остановить
sudo systemctl restart sylph-bot   # перезапустить
sudo systemctl status sylph-bot    # статус
sudo journalctl -u sylph-bot -n 50 # последние 50 строк логов
```

---

## Технологии

- **Python 3.11+**
- **[aiogram 3.x](https://docs.aiogram.dev/)** — асинхронный фреймворк для Telegram Bot API
- **[httpx](https://www.python-httpx.org/)** — асинхронный HTTP-клиент
- **[AgentRouter](https://agentrouter.org)** — OpenAI-совместимый LLM gateway
- **python-dotenv** — загрузка переменных окружения из `.env`

## Лицензия

MIT
