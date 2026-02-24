"""
Telegram Username Monitor Bot - Enterprise Grade
Main bot implementation
"""

import asyncio
import logging
import threading
from flask import Flask
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import BOT_TOKEN, OWNER_ID, PORT
from src.database import DatabaseManager
from src.monitor import InstagramMonitor
from src.utils import setup_logging

# Rest of the bot code from previous response...
# (Copy all the classes: BotUser, MonitoredUser, UsernameMonitorBot)
# Make sure to update imports to use src.config
