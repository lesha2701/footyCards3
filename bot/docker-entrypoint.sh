#!/bin/sh
set -e

echo "Waiting for database..."
python -c "
import asyncio
import sys
import time

import asyncpg
from config import get_bot_settings

async def wait_for_db():
    settings = get_bot_settings()
    for attempt in range(30):
        try:
            conn = await asyncpg.connect(settings.asyncpg_dsn)
            await conn.close()
            print('Database is ready.')
            return
        except Exception as exc:
            print(f'Database not ready (attempt {attempt + 1}/30): {exc}')
            time.sleep(2)
    print('Database did not become ready in time', file=sys.stderr)
    sys.exit(1)

asyncio.run(wait_for_db())
"

echo "Starting bot: $@"
exec "$@"
