import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

LIVE_MODE = os.getenv("LIVE_MODE", "false").lower() == "true"
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("PORT", os.getenv("API_PORT", "8001")))
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), '..', 'trading.db'))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
SYSTEM_CYCLE_SECONDS = int(os.getenv("SYSTEM_CYCLE_SECONDS", "60"))
MAX_CONCURRENT_TRADES = int(os.getenv("MAX_CONCURRENT_TRADES", "100"))
ENABLE_BACKGROUND_LOOP = os.getenv("ENABLE_BACKGROUND_LOOP", "true").lower() == "true"

STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "2.0"))
TRAILING_STOP_PCT = float(os.getenv("TRAILING_STOP_PCT", "1.5"))
TRADE_UPDATE_INTERVAL = int(os.getenv("TRADE_UPDATE_INTERVAL", "60"))
BROKER_FEE_PCT = float(os.getenv("BROKER_FEE_PCT", "0.1"))

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE_PATH = os.path.join(BACKEND_DIR, '.env')
