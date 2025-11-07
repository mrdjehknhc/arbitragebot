"""
Helper functions
"""
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any
import pytz
import time

def generate_trade_id() -> str:
    """Генерирует уникальный ID сделки с микросекундами"""
    timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    microseconds = int(time.time() * 1000000) % 1000000
    return f"ARB-{timestamp}-{microseconds:06d}"

def generate_opportunity_id() -> str:
    """Генерирует уникальный ID возможности с микросекундами"""
    timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    microseconds = int(time.time() * 1000000) % 1000000
    return f"OPP-{timestamp}-{microseconds:06d}"

def calculate_profit_percent(start_amount: float, end_amount: float) -> float:
    """Рассчитывает процент прибыли"""
    if start_amount == 0:
        return 0.0
    return ((end_amount - start_amount) / start_amount) * 100

def calculate_fees(amount: float, fee_rate: float) -> float:
    """Рассчитывает комиссию"""
    return amount * fee_rate

def format_currency(amount: float, precision: int = 2) -> str:
    """Форматирует сумму в валюте"""
    return f"${amount:,.{precision}f}"

def format_percent(value: float, precision: int = 2) -> str:
    """Форматирует процент"""
    return f"{value:.{precision}f}%"

def get_utc_now() -> datetime:
    """Возвращает текущее время UTC"""
    return datetime.now(pytz.UTC)

def format_timestamp(dt: datetime = None) -> str:
    """Форматирует timestamp"""
    if dt is None:
        dt = get_utc_now()
    return dt.strftime('%Y-%m-%d %H:%M:%S UTC')