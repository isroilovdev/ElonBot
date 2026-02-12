"""
Configuration file for Telegram automation bot
"""

# Bot token from @BotFather
BOT_TOKEN = "6997192105:AAFQw3Z9umfIpDShP2aWnGuNt5MiJx9iWOg"

# Admin user IDs (Telegram user IDs)
ADMIN_IDS = [6700049540]

# Admin contact for subscription requests
ADMIN_CONTACT = "@ID_6969"

# Database settings
DB_PATH = "bot.db"

# Session directory for Telethon
SESSION_DIR = "sessions/"

# Random interval settings (in seconds)
DEFAULT_RANDOM_INTERVAL_MIN = 315  # 5 minutes
DEFAULT_RANDOM_INTERVAL_MAX = 435  # 6 minutes

# Telegram API credentials (get from https://my.telegram.org)
API_ID = 38103519
API_HASH = "72a364bfef4d5b24e5861cf55e4a25f1"

# Safety settings to prevent traffic issues
MAX_RETRY_ATTEMPTS = 5
BASE_RETRY_DELAY = 10  # seconds
MAX_RETRY_DELAY = 100  # seconds
BROADCAST_DELAY_MIN = 2.0  # seconds between broadcast messages
BROADCAST_DELAY_MAX = 5.0