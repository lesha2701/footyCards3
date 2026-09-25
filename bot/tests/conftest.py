import os
import sys
from pathlib import Path

# Make `services.*`, `config`, `keyboards` importable when pytest runs from bot/ or elsewhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Dummy values only; never read a real .env.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "0:TEST")
os.environ.setdefault("INTERNAL_API_SECRET", "test_secret")
os.environ.setdefault("MINI_APP_URL", "https://app.example.test")
