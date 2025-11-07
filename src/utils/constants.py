"""
Constants and static data for the bot
"""

# Exchange names
EXCHANGES = ['bybit', 'binance', 'okx', 'kucoin', 'gateio']

# Arbitrage types
ARB_TYPES = {
    'TRIANGULAR': 'triangular',
    'CROSS_EXCHANGE': 'cross_exchange',
    'MULTI_HOP': 'multi_hop'
}

# Trade status
TRADE_STATUS = {
    'SUCCESS': 'success',
    'FAILED': 'failed',
    'PARTIAL': 'partial',
    'PENDING': 'pending'
}

# Default trading fees (%)
DEFAULT_FEES = {
    'bybit': 0.1,
    'binance': 0.1,
    'okx': 0.08,
    'kucoin': 0.1,
    'gateio': 0.2
}

# Minimum trading amounts (USD)
MIN_TRADE_AMOUNTS = {
    'bybit': 10,
    'binance': 10,
    'okx': 10,
    'kucoin': 10,
    'gateio': 10
}

# API rate limits (requests per second)
RATE_LIMITS = {
    'bybit': 10,
    'binance': 10,
    'okx': 20,
    'kucoin': 10,
    'gateio': 10
}

# Stablecoins
STABLECOINS = ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDD']

# Major coins (always include)
MAJOR_COINS = ['BTC', 'ETH', 'BNB', 'SOL', 'XRP']

# Fiat currencies (usually excluded)
FIAT_CURRENCIES = [
    'USD', 'EUR', 'GBP', 'JPY', 'CNY', 'KRW',
    'RUB', 'AUD', 'CAD', 'CHF', 'HKD', 'SGD'
]

# Liquidity score thresholds
LIQUIDITY_SCORES = {
    'HIGH': 80,
    'MEDIUM': 50,
    'LOW': 0
}

# Time constants
SECONDS_IN_DAY = 86400
SECONDS_IN_HOUR = 3600
SECONDS_IN_MINUTE = 60

# Profit thresholds (%)
MIN_PROFIT = 0.3  # Minimum to consider
GOOD_PROFIT = 1.0  # Good opportunity
EXCELLENT_PROFIT = 2.0  # Excellent opportunity

# Database
DB_PATH = 'data/arb_bot.db'
REPORTS_DIR = 'data/reports'

# Logs
LOG_FORMAT = '{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} | {message}'
LOG_DIR = 'logs'

# Telegram message limits
TG_MAX_MESSAGE_LENGTH = 4096

# CSV Report headers (with emojis for crypto vibe)
CSV_HEADERS = {
    'weekly': [
        '🆔 Trade ID',
        '📅 Date',
        '⏰ Time UTC',
        '🏦 Exchange',
        '📊 Type',
        '💰 Profit %',
        '💵 Profit USD',
        '📈 Trade Size',
        '⚡ Exec Time',
        '🎯 Status'
    ],
    'monthly': [
        'Date',
        'Trade ID',
        'Exchange',
        'Type',
        'Expected %',
        'Actual %',
        'Profit USD',
        'Size USD',
        'Exec Time',
        'Status'
    ]
}