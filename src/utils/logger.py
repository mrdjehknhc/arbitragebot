"""
Clean logging system with loguru
"""
import sys
from pathlib import Path
from loguru import logger

# Create logs directory
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Remove default handler
logger.remove()

# Console handler (colored output)
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>",
    level="INFO",
    colorize=True
)

# File handler - main log
logger.add(
    LOG_DIR / "bot.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
    compression="zip"
)

# File handler - trades only
logger.add(
    LOG_DIR / "trades.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    level="INFO",
    rotation="5 MB",
    retention="30 days",
    filter=lambda record: "trade" in record["extra"]
)

# File handler - errors only
logger.add(
    LOG_DIR / "errors.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}\n{exception}",
    level="ERROR",
    rotation="5 MB",
    retention="30 days"
)

# File handler - telegram notifications
logger.add(
    LOG_DIR / "telegram.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
    level="INFO",
    rotation="5 MB",
    retention="7 days",
    filter=lambda record: "telegram" in record["extra"]
)

def get_logger():
    """Returns configured logger instance"""
    return logger