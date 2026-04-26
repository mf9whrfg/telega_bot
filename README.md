# telega_bot

Простой Telegram-бот, который повторяет любое сообщение пользователя.

## Установка

1. Установите зависимости:

```bash
python3 -m pip install -r requirements.txt
```

2. Создайте бота через BotFather и получите токен.
3. Установите переменную окружения:

```bash
export TELEGRAM_BOT_TOKEN="<ваш_токен>"
```

4. Запустите бота:

```bash
python3 bot.py
```

## Использование

Напишите боту любое сообщение — он ответит тем же текстом.

## Деплой на Render

1. Зарегистрируйтесь на [Render](https://render.com).
2. Подключите ваш GitHub репозиторий.
3. Создайте новый Web Service.
4. Выберите репозиторий `telega_bot`.
5. В настройках укажите:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
6. Добавьте переменную окружения `TELEGRAM_BOT_TOKEN` с вашим токеном бота.
7. Разверните сервис.

Бот будет доступен по HTTPS URL, но Telegram будет общаться через API.
