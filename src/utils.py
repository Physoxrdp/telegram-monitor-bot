import logging
from src.config import LOG_LEVEL, LOG_FORMAT  # Ab ye sahi hai

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        format=LOG_FORMAT,
        level=getattr(logging, LOG_LEVEL),
        handlers=[
            logging.FileHandler("logs/bot.log"),
            logging.StreamHandler()
        ]
    )

def format_number(num: int) -> str:
    """Format number with commas"""
    return f"{num:,}"

def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to max length"""
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text
