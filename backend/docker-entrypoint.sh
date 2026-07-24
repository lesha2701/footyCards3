#!/bin/sh
set -e

echo "Waiting for database..."
python -c "
import asyncio
import sys
import time

from app.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine

async def wait_for_db():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    for attempt in range(30):
        try:
            async with engine.connect() as conn:
                await conn.execute(__import__('sqlalchemy').text('SELECT 1'))
            print('Database is ready.')
            return
        except Exception as exc:
            print(f'Database not ready (attempt {attempt + 1}/30): {exc}')
            time.sleep(2)
    print('Database did not become ready in time', file=sys.stderr)
    sys.exit(1)

asyncio.run(wait_for_db())
"

echo "Running database migrations..."
alembic upgrade head

echo "Starting application: $@"
exec "$@"
