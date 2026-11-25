# Adrobot

Система управления рекламными кампаниями Keitaro.

## Стек

- Python 3.12
- FastAPI
- SQLAlchemy 2.x
- PostgreSQL 17
- Alembic
- React
- Vite
- Docker Compose

## Запуск

Создать конфигурацию:

    cp .env.example .env

Запустить приложение:

    docker compose up -d --build

Frontend:

    http://localhost:5173

Backend:

    http://localhost:8000

Swagger:

    http://localhost:8000/docs

## Остановка

    docker compose down

## Логи

    docker compose logs -f

## Миграции

Будут добавлены при настройке Alembic.