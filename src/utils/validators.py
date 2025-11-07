"""
Input validation utilities
Professional data validation with clear error messages
"""
from typing import Any, List, Dict, Optional, Union
from decimal import Decimal, InvalidOperation
import re


class ValidationError(Exception):
    """Custom validation error"""
    pass


class Validators:
    """Collection of validation methods"""
    
    @staticmethod
    def validate_exchange_name(name: str) -> str:
        """
        Validate exchange name
        
        Args:
            name: Exchange name
        
        Returns:
            Validated lowercase name
        
        Raises:
            ValidationError: If invalid
        """
        if not name or not isinstance(name, str):
            raise ValidationError("Exchange name must be non-empty string")
        
        name = name.lower().strip()
        
        valid_exchanges = {
            'bybit', 'binance', 'okx', 'kucoin', 'gateio',
            'huobi', 'kraken', 'coinbase', 'bitfinex'
        }
        
        if name not in valid_exchanges:
            raise ValidationError(
                f"Unknown exchange: {name}. "
                f"Supported: {', '.join(sorted(valid_exchanges))}"
            )
        
        return name
    
    @staticmethod
    def validate_symbol(symbol: str) -> str:
        """
        Validate trading pair symbol
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
        
        Returns:
            Validated symbol
        
        Raises:
            ValidationError: If invalid
        """
        if not symbol or not isinstance(symbol, str):
            raise ValidationError("Symbol must be non-empty string")
        
        symbol = symbol.upper().strip()
        
        # Check format: BASE/QUOTE
        if '/' not in symbol:
            raise ValidationError(
                f"Invalid symbol format: {symbol}. "
                "Expected format: BASE/QUOTE (e.g., BTC/USDT)"
            )
        
        parts = symbol.split('/')
        if len(parts) != 2:
            raise ValidationError(
                f"Invalid symbol: {symbol}. "
                "Must have exactly one '/' separator"
            )
        
        base, quote = parts
        
        if not base or not quote:
            raise ValidationError(f"Empty base or quote in symbol: {symbol}")
        
        if not re.match(r'^[A-Z0-9]+$', base):
            raise ValidationError(f"Invalid base currency: {base}")
        
        if not re.match(r'^[A-Z0-9]+$', quote):
            raise ValidationError(f"Invalid quote currency: {quote}")
        
        return symbol
    
    @staticmethod
    def validate_amount(
        amount: Union[int, float, str, Decimal],
        min_value: float = 0.0,
        max_value: Optional[float] = None,
        allow_zero: bool = False
    ) -> float:
        """
        Validate trading amount
        
        Args:
            amount: Amount to validate
            min_value: Minimum allowed value
            max_value: Maximum allowed value (optional)
            allow_zero: Allow zero values
        
        Returns:
            Validated amount as float
        
        Raises:
            ValidationError: If invalid
        """
        try:
            amount = float(amount)
        except (TypeError, ValueError, InvalidOperation):
            raise ValidationError(f"Invalid amount: {amount}. Must be numeric")
        
        if not allow_zero and amount == 0:
            raise ValidationError("Amount cannot be zero")
        
        if amount < min_value:
            raise ValidationError(
                f"Amount {amount} below minimum {min_value}"
            )
        
        if max_value is not None and amount > max_value:
            raise ValidationError(
                f"Amount {amount} exceeds maximum {max_value}"
            )
        
        if amount < 0:
            raise ValidationError(f"Amount cannot be negative: {amount}")
        
        return amount
    
    @staticmethod
    def validate_price(price: Union[int, float, str, Decimal]) -> float:
        """
        Validate price
        
        Args:
            price: Price to validate
        
        Returns:
            Validated price as float
        
        Raises:
            ValidationError: If invalid
        """
        try:
            price = float(price)
        except (TypeError, ValueError, InvalidOperation):
            raise ValidationError(f"Invalid price: {price}. Must be numeric")
        
        if price <= 0:
            raise ValidationError(f"Price must be positive: {price}")
        
        return price
    
    @staticmethod
    def validate_percentage(
        value: Union[int, float, str],
        min_pct: float = 0.0,
        max_pct: float = 100.0
    ) -> float:
        """
        Validate percentage value
        
        Args:
            value: Percentage to validate
            min_pct: Minimum percentage
            max_pct: Maximum percentage
        
        Returns:
            Validated percentage
        
        Raises:
            ValidationError: If invalid
        """
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValidationError(
                f"Invalid percentage: {value}. Must be numeric"
            )
        
        if value < min_pct or value > max_pct:
            raise ValidationError(
                f"Percentage {value} outside valid range "
                f"[{min_pct}, {max_pct}]"
            )
        
        return value
    
    @staticmethod
    def validate_path(path: List[tuple]) -> List[tuple]:
        """
        Validate arbitrage path
        
        Args:
            path: List of (from_currency, to_currency) tuples
        
        Returns:
            Validated path
        
        Raises:
            ValidationError: If invalid
        """
        if not path or not isinstance(path, list):
            raise ValidationError("Path must be non-empty list")
        
        if len(path) < 2:
            raise ValidationError(
                f"Path too short: {len(path)} steps. Minimum: 2"
            )
        
        if len(path) > 10:
            raise ValidationError(
                f"Path too long: {len(path)} steps. Maximum: 10"
            )
        
        for i, step in enumerate(path):
            if not isinstance(step, (tuple, list)) or len(step) != 2:
                raise ValidationError(
                    f"Invalid step {i}: {step}. "
                    "Expected (from_currency, to_currency)"
                )
            
            from_cur, to_cur = step
            if not from_cur or not to_cur:
                raise ValidationError(f"Empty currency in step {i}: {step}")
            
            if from_cur == to_cur:
                raise ValidationError(
                    f"Invalid step {i}: same currency {from_cur}"
                )
        
        # Check path is closed (forms a cycle)
        first_currency = path[0][0]
        last_currency = path[-1][1]
        
        if first_currency != last_currency:
            raise ValidationError(
                f"Path not closed: starts with {first_currency}, "
                f"ends with {last_currency}"
            )
        
        return path
    
    @staticmethod
    def validate_orderbook(orderbook: Dict) -> Dict:
        """
        Validate orderbook structure
        
        Args:
            orderbook: Orderbook dict from exchange
        
        Returns:
            Validated orderbook
        
        Raises:
            ValidationError: If invalid
        """
        if not isinstance(orderbook, dict):
            raise ValidationError("Orderbook must be dict")
        
        required_keys = ['bids', 'asks']
        for key in required_keys:
            if key not in orderbook:
                raise ValidationError(f"Missing '{key}' in orderbook")
            
            if not isinstance(orderbook[key], list):
                raise ValidationError(f"Orderbook '{key}' must be list")
            
            if not orderbook[key]:
                raise ValidationError(f"Empty '{key}' in orderbook")
            
            # Validate first order format [price, amount]
            first_order = orderbook[key][0]
            if not isinstance(first_order, (list, tuple)) or len(first_order) < 2:
                raise ValidationError(
                    f"Invalid order format in '{key}': {first_order}"
                )
            
            try:
                price = float(first_order[0])
                amount = float(first_order[1])
                
                if price <= 0 or amount <= 0:
                    raise ValidationError(
                        f"Invalid price/amount in '{key}': {first_order}"
                    )
            except (TypeError, ValueError):
                raise ValidationError(
                    f"Non-numeric price/amount in '{key}': {first_order}"
                )
        
        return orderbook
    
    @staticmethod
    def validate_balance(balance: Dict[str, float]) -> Dict[str, float]:
        """
        Validate balance dict
        
        Args:
            balance: Balance dict {currency: amount}
        
        Returns:
            Validated balance
        
        Raises:
            ValidationError: If invalid
        """
        if not isinstance(balance, dict):
            raise ValidationError("Balance must be dict")
        
        validated = {}
        
        for currency, amount in balance.items():
            if not isinstance(currency, str) or not currency:
                raise ValidationError(f"Invalid currency: {currency}")
            
            try:
                amount = float(amount)
            except (TypeError, ValueError):
                raise ValidationError(
                    f"Invalid amount for {currency}: {amount}"
                )
            
            if amount < 0:
                raise ValidationError(
                    f"Negative balance for {currency}: {amount}"
                )
            
            if amount > 0:  # Only include non-zero balances
                validated[currency.upper()] = amount
        
        return validated
    
    @staticmethod
    def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate configuration dict
        
        Args:
            config: Configuration dict
        
        Returns:
            Validated config
        
        Raises:
            ValidationError: If invalid
        """
        if not isinstance(config, dict):
            raise ValidationError("Config must be dict")
        
        required_sections = ['exchanges', 'strategy', 'trading', 'risk']
        
        for section in required_sections:
            if section not in config:
                raise ValidationError(f"Missing config section: {section}")
            
            if not isinstance(config[section], dict):
                raise ValidationError(
                    f"Config section '{section}' must be dict"
                )
        
        # Validate strategy params
        strategy = config['strategy']
        
        if 'min_profit_percent' in strategy:
            strategy['min_profit_percent'] = Validators.validate_percentage(
                strategy['min_profit_percent'],
                min_pct=0.0,
                max_pct=100.0
            )
        
        if 'max_path_length' in strategy:
            max_len = strategy['max_path_length']
            if not isinstance(max_len, int) or max_len < 2 or max_len > 10:
                raise ValidationError(
                    f"Invalid max_path_length: {max_len}. Must be 2-10"
                )
        
        # Validate trading params
        trading = config['trading']
        
        if 'trade_size_usd' in trading:
            trading['trade_size_usd'] = Validators.validate_amount(
                trading['trade_size_usd'],
                min_value=10.0
            )
        
        # Validate risk params
        risk = config['risk']
        
        if 'max_daily_loss_usd' in risk:
            risk['max_daily_loss_usd'] = Validators.validate_amount(
                risk['max_daily_loss_usd'],
                min_value=0.0
            )
        
        return config
    
    @staticmethod
    def sanitize_string(value: str, max_length: int = 255) -> str:
        """
        Sanitize string input
        
        Args:
            value: String to sanitize
            max_length: Maximum allowed length
        
        Returns:
            Sanitized string
        """
        if not isinstance(value, str):
            value = str(value)
        
        # Remove control characters
        value = re.sub(r'[\x00-\x1F\x7F]', '', value)
        
        # Trim whitespace
        value = value.strip()
        
        # Truncate if too long
        if len(value) > max_length:
            value = value[:max_length]
        
        return value


# Convenience functions
def validate_trade_params(
    exchange: str,
    symbol: str,
    amount: float,
    price: float
) -> Dict[str, Any]:
    """
    Validate all trade parameters at once
    
    Returns:
        Dict with validated params
    
    Raises:
        ValidationError: If any param invalid
    """
    return {
        'exchange': Validators.validate_exchange_name(exchange),
        'symbol': Validators.validate_symbol(symbol),
        'amount': Validators.validate_amount(amount),
        'price': Validators.validate_price(price)
    }


def is_valid_opportunity(opp: Dict) -> bool:
    """
    Check if opportunity dict is valid
    
    Args:
        opp: Opportunity dict
    
    Returns:
        True if valid, False otherwise
    """
    try:
        required_keys = [
            'id', 'type', 'exchange', 'path',
            'profit_percent', 'expected_profit_usd'
        ]
        
        for key in required_keys:
            if key not in opp:
                return False
        
        if opp['profit_percent'] <= 0:
            return False
        
        if not isinstance(opp['path'], list) or len(opp['path']) < 2:
            return False
        
        return True
        
    except Exception:
        return False