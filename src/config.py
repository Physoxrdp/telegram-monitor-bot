import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
PORT = int(os.getenv("PORT", 8080))

# File paths
DATA_FILE = "data/bot_data.json"

# Monitoring settings
MONITOR_INTERVAL = 300  # 5 minutes
CONFIRMATION_THRESHOLD = 3  # Triple confirmation

# User limits
DEFAULT_USER_LIMIT = 20

# API settings
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
