FROM python:3.11-slim

WORKDIR /app

# Копирование файлов
COPY requirements.txt .
COPY bot.py .
COPY config.py .
COPY .env .

# Установка зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Запуск бота
CMD ["python", "bot.py"]