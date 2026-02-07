# Telegram Bot для загрузки на Яндекс Диск - Дизайн

**Дата:** 2026-02-07
**Статус:** Утверждён

## Обзор

Telegram бот для загрузки файлов на Яндекс Диск с использованием OAuth-токена пользователя. Модульная архитектура для лёгкого расширения (GitHub, AI чат в будущем).

## Требования

### Функциональные
- ✅ Все типы файлов (документы, фото, видео, архивы)
- ✅ Максимум 2 GB на файл (Telegram Premium)
- ✅ Пользователь создаёт и называет папку для файлов
- ✅ Шифрование OAuth токенов (Fernet)
- ✅ Простые сообщения об ошибках без retry
- ✅ Прогресс-бар загрузки
- ✅ Список загруженных файлов (/list)
- ✅ Удаление файлов через бота (/delete)

### Технические
- Python 3.11+
- aiogram 3 (async)
- SQLAlchemy + SQLite
- aiohttp для Yandex API
- Cryptography (Fernet) для токенов

---

## Архитектура

### Модульная структура

```
bot/
├── core/                   # Ядро приложения
│   ├── bot.py             # Инициализация aiogram
│   ├── database.py        # SQLAlchemy setup
│   ├── crypto.py          # Шифрование токенов
│   └── middleware.py      # Auth, logging, rate limit
│
├── modules/               # Независимые модули
│   ├── yandex/           # Модуль Яндекс Диска
│   │   ├── __init__.py   # Регистрация модуля
│   │   ├── handlers.py   # Telegram handlers
│   │   ├── service.py    # Yandex API client
│   │   ├── models.py     # БД модели
│   │   ├── keyboards.py  # UI клавиатуры
│   │   └── utils.py      # Вспомогательные функции
│   │
│   ├── github/           # Будущий модуль
│   ├── ai_chat/          # Будущий модуль
│   └── common/           # Базовые команды (/start, /help)
│
├── config.py             # Конфигурация
├── main.py              # Точка входа
└── requirements.txt
```

### Принципы
- **Модульность:** каждый модуль независим, подключается через `setup()`
- **Расширяемость:** новые модули добавляются без изменения существующих
- **Безопасность:** токены шифруются, временные файлы удаляются
- **Асинхронность:** полностью async для производительности

---

## Компоненты

### 1. Core (Ядро)

**core/bot.py** - Инициализация бота:
```python
class BotCore:
    - Создание Bot и Dispatcher
    - Регистрация middleware
    - Загрузка модулей
    - Запуск polling
```

**core/database.py** - Единая БД:
```python
- SQLAlchemy Base
- Session management
- create_tables()
```

**core/crypto.py** - Шифрование:
```python
class TokenEncryption:
    - encrypt(token: str) -> str
    - decrypt(encrypted: str) -> str
    # Использует Fernet
```

**core/middleware.py**:
- `AuthMiddleware` - проверка регистрации
- `LoggingMiddleware` - логирование событий
- `RateLimitMiddleware` - 5 req/sec

---

### 2. Модуль Yandex Disk

#### Модели данных

**YandexToken:**
- user_id (PK)
- encrypted_token
- folder_name (default: 'TelegramBot')
- created_at
- is_valid

**UploadedFile:**
- id (PK)
- user_id
- file_name
- yandex_path
- public_url
- file_size
- uploaded_at

#### API Service

**YandexDiskAPI:**
```python
async def check_token() -> bool
async def create_folder(path: str) -> bool
async def get_upload_url(path: str) -> str
async def upload_file(url, file_path, progress_callback)
async def publish_file(path: str) -> str
async def delete_file(path: str) -> bool
```

#### Handlers

**Команды:**
- `/token` - ввод OAuth токена (FSM)
  - Проверка валидности через API
  - Шифрование и сохранение в БД
  - Удаление сообщения с токеном для безопасности

- Создание папки (FSM)
  - Callback кнопка или ввод названия
  - Создание через API
  - Сохранение folder_name в БД

- **Загрузка файла** (любой тип медиа):
  1. Проверка наличия токена
  2. Скачивание из Telegram во временную папку
  3. Получение upload_url от Yandex
  4. Загрузка с прогресс-баром (chunked)
  5. Публикация файла
  6. Сохранение метаданных в БД
  7. Отправка публичной ссылки
  8. Очистка временного файла

- `/list` - список файлов
  - Последние 10 файлов с inline кнопками
  - Формат: название, размер, дата

- `/delete` - удаление файла
  - Callback с подтверждением
  - Удаление с Yandex Disk
  - Удаление из БД

#### UI

**Клавиатуры:**
- Выбор папки (создать / корневая)
- Список файлов с кнопками удаления
- Подтверждение удаления

**Прогресс-бар:**
```
⏳ Загружаю файл на Яндекс Диск...
[████████░░] 80%
```

#### Utils

- `create_progress_bar(percent)` - визуализация
- `format_size(bytes)` - человекочитаемый размер
- `download_telegram_file()` - скачивание во временную папку
- `cleanup_temp_file()` - удаление временных файлов
- `cleanup_old_temp_files()` - фоновая очистка (24ч)

---

### 3. Базовые команды

**modules/common/handlers.py:**
- `/start` - приветствие, инструкция
- `/help` - подробная справка по использованию

---

## Поток данных

### Регистрация пользователя
```
/start → /token → [ввод токена] → проверка API → шифрование →
→ сохранение в БД → выбор папки → создание папки → готов к работе
```

### Загрузка файла
```
[файл в Telegram] → проверка токена → скачивание →
→ get_upload_url → chunked upload с прогресс-баром →
→ publish → сохранение в БД → публичная ссылка → очистка
```

### Просмотр и удаление
```
/list → запрос из БД → inline клавиатура →
→ callback delete_X → подтверждение → API delete → БД delete
```

---

## Безопасность

### Токены
- Шифрование Fernet перед сохранением в БД
- Ключ шифрования в переменной окружения `ENCRYPTION_KEY`
- Удаление сообщений с токенами сразу после получения

### Файлы
- Временные файлы в `/tmp/telegram_bot_files`
- Удаление сразу после загрузки
- Фоновая очистка старых файлов (24ч)

### Rate Limiting
- Middleware: 5 запросов/секунду на пользователя
- Защита от спама

### Валидация
- Проверка токена перед сохранением
- Проверка владения файлом перед удалением
- Лимит размера файла 2GB

---

## Обработка ошибок

### Стратегия
Простые сообщения без автоповтора (по требованиям)

### Сценарии
- **Невалидный токен:** "❌ Неверный токен. Попробуйте ещё раз /token"
- **Нет места на диске:** "❌ Недостаточно места на Яндекс Диске"
- **Сетевая ошибка:** "❌ Ошибка загрузки. Проверьте подключение"
- **Файл слишком большой:** "❌ Файл слишком большой (макс 2 GB)"
- **Токен не настроен:** "⚠️ Сначала настройте токен: /token"

---

## Конфигурация

**config.py:**
```python
BOT_TOKEN              # Telegram bot token
ENCRYPTION_KEY         # Fernet key для шифрования
YANDEX_CLIENT_ID       # Для инструкций пользователям
DATABASE_URL           # sqlite:///bot.db
MAX_FILE_SIZE          # 2 GB
RATE_LIMIT             # 5 req/sec
TEMP_DIR               # /tmp/telegram_bot_files
CLEANUP_INTERVAL_HOURS # 24
ENABLED_MODULES        # ['yandex']
```

**Переменные окружения (.env):**
```
BOT_TOKEN=...
ENCRYPTION_KEY=...
YANDEX_CLIENT_ID=...
```

---

## Deployment

### Docker
```yaml
services:
  bot:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./bot.db:/app/bot.db
```

### Systemd (VPS)
```ini
[Service]
ExecStart=/opt/yandex_bot/venv/bin/python main.py
Restart=always
```

### Требования к хостингу
- Python 3.11+
- 1GB RAM (минимум)
- 10GB диск (для логов и временных файлов)
- Ubuntu 20.04+ или Docker

---

## Расширение в будущем

### GitHub модуль
```python
modules/github/
├── handlers.py   # /repo, /issue, /pr, /gist
├── service.py    # GitHub API client
└── models.py     # repos, issues, gists
```

### AI Chat модуль
```python
modules/ai_chat/
├── handlers.py   # /chat, /ask, context management
├── service.py    # OpenAI/Anthropic API
└── models.py     # conversations, messages
```

### Общие сервисы (для переиспользования)
- `FileStorage` - работа с временными файлами
- `TaskQueue` - очередь тяжёлых операций
- `Analytics` - метрики использования

---

## Метрики успеха

- ✅ Загрузка файла < 30 сек для 100MB
- ✅ Прогресс-бар обновляется каждые 10%
- ✅ Токены зашифрованы и недоступны в plaintext
- ✅ Временные файлы удаляются автоматически
- ✅ Модули изолированы (можно отключить Yandex - бот работает)

---

## Следующие шаги

1. **Создать структуру проекта** - директории, файлы
2. **Реализовать Core** - bot.py, database.py, crypto.py, middleware.py
3. **Реализовать Yandex модуль** - models → service → handlers
4. **Реализовать Common модули** - /start, /help
5. **Настроить main.py** - точка входа, загрузка модулей
6. **Тестирование** - локальный запуск, реальный токен
7. **Deployment** - Docker / systemd на VPS
8. **Мониторинг** - логи, ошибки

---

## Примечания

- Дизайн одобрен 2026-02-07
- Приоритет: простота и расширяемость
- YAGNI: только необходимый функционал в первой версии
- Безопасность: шифрование обязательно
