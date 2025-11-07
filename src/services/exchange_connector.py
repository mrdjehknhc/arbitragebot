"""
Async exchange connector with rate limiting and error handling
Professional wrapper around CCXT with async support
"""
import ccxt.async_support as ccxt_async
import asyncio
from typing import Dict, List, Optional, Any, Set
from decimal import Decimal
from ..utils.logger import get_logger
from ..utils.async_helpers import RateLimiter, async_retry, AsyncCache
from ..utils.validators import Validators, ValidationError

logger = get_logger()


class ExchangeConnector:
    """
    Async wrapper for CCXT exchanges
    Handles rate limiting, caching, and error recovery
    """
    
    # Rate limits per exchange (requests per second)
    RATE_LIMITS = {
        'bybit': 10,
        'binance': 10,
        'okx': 20,
        'kucoin': 10,
        'gateio': 10,
        'huobi': 10,
        'kraken': 5
    }
    
    def __init__(self, exchange_name: str, config: Dict):
        """
        Initialize exchange connector
        
        Args:
            exchange_name: Exchange name (e.g., 'bybit')
            config: Exchange config from config.yml
        """
        self.name = Validators.validate_exchange_name(exchange_name)
        self.config = config
        
        # Rate limiter
        rate_limit = self.RATE_LIMITS.get(self.name, 10)
        self.rate_limiter = RateLimiter(calls_per_second=rate_limit)
        
        # Cache with 10s TTL for tickers, 30s for markets
        self.ticker_cache = AsyncCache(ttl=10.0)
        self.market_cache = AsyncCache(ttl=30.0)
        self.orderbook_cache = AsyncCache(ttl=5.0)
        
        # CCXT instance (will be created async)
        self.exchange: Optional[ccxt_async.Exchange] = None
        self._initialized = False
        
        # Markets data
        self.markets: Dict = {}
        self.symbols: Set[str] = set()
        
        logger.info(f"📡 ExchangeConnector initialized for {self.name.upper()}")
    
    async def initialize(self):
        """
        Initialize async exchange connection
        Must be called before any other operations
        """
        if self._initialized:
            return
        
        try:
            # Create CCXT instance
            self.exchange = await self._create_exchange()
            
            # Load markets
            self.markets = await self._load_markets()
            self.symbols = set(self.markets.keys())
            
            self._initialized = True
            logger.info(f"✅ {self.name.upper()} connected: {len(self.symbols)} symbols")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize {self.name}: {e}")
            raise
    
    async def _create_exchange(self) -> ccxt_async.Exchange:
        """Create CCXT exchange instance"""
        api_key = self.config.get('api_key', '')
        api_secret = self.config.get('api_secret', '')
        testnet = self.config.get('testnet', False)
        
        # Base params
        params = {
            'enableRateLimit': True,
            'timeout': 30000,
            'options': {'defaultType': 'spot'}
        }
        
        # Add API credentials if available
        if api_key and api_secret:
            params['apiKey'] = api_key
            params['secret'] = api_secret
        
        # Create exchange
        if self.name == 'bybit':
            exchange = ccxt_async.bybit(params)
        elif self.name == 'binance':
            exchange = ccxt_async.binance(params)
        elif self.name == 'okx':
            passphrase = self.config.get('passphrase', '')
            if passphrase:
                params['password'] = passphrase
            exchange = ccxt_async.okx(params)
        elif self.name == 'kucoin':
            passphrase = self.config.get('passphrase', '')
            if passphrase:
                params['password'] = passphrase
            exchange = ccxt_async.kucoin(params)
        elif self.name == 'gateio':
            exchange = ccxt_async.gateio(params)
        else:
            raise ValueError(f"Unsupported exchange: {self.name}")
        
        # Set sandbox mode if testnet
        if testnet:
            exchange.set_sandbox_mode(True)
            logger.info(f"🧪 {self.name.upper()} in TESTNET mode")
        
        return exchange
    
    async def _load_markets(self) -> Dict:
        """Load and cache markets"""
        cache_key = f"{self.name}_markets"
        cached = await self.market_cache.get(cache_key)
        
        if cached:
            return cached
        
        await self.rate_limiter.acquire()
        markets = await async_retry(
            lambda: self.exchange.load_markets(),
            max_attempts=3
        )
        
        await self.market_cache.set(cache_key, markets)
        return markets
    
    async def fetch_ticker(self, symbol: str) -> Optional[Dict]:
        """
        Fetch single ticker with caching
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
        
        Returns:
            Ticker dict or None on error
        """
        try:
            symbol = Validators.validate_symbol(symbol)
        except ValidationError as e:
            logger.warning(f"Invalid symbol: {e}")
            return None
        
        if symbol not in self.symbols:
            logger.warning(f"{symbol} not available on {self.name}")
            return None
        
        cache_key = f"{self.name}_{symbol}_ticker"
        
        async def _fetch():
            await self.rate_limiter.acquire()
            return await self.exchange.fetch_ticker(symbol)
        
        try:
            return await self.ticker_cache.get_or_fetch(cache_key, _fetch)
        except Exception as e:
            logger.error(f"Error fetching ticker {symbol} from {self.name}: {e}")
            return None
    
    async def fetch_tickers(self, symbols: Optional[List[str]] = None) -> Dict[str, Dict]:
        """
        Fetch multiple tickers (parallel if possible)
        
        Args:
            symbols: List of symbols to fetch, or None for all
        
        Returns:
            Dict {symbol: ticker_data}
        """
        try:
            await self.rate_limiter.acquire()
            
            # Try batch fetch first (faster)
            if symbols is None:
                tickers = await async_retry(
                    lambda: self.exchange.fetch_tickers(),
                    max_attempts=2
                )
            else:
                # Validate symbols
                valid_symbols = []
                for s in symbols:
                    try:
                        s = Validators.validate_symbol(s)
                        if s in self.symbols:
                            valid_symbols.append(s)
                    except ValidationError:
                        continue
                
                if not valid_symbols:
                    return {}
                
                # Try batch fetch
                try:
                    tickers = await self.exchange.fetch_tickers(valid_symbols)
                except Exception:
                    # Fallback to individual fetches
                    tickers = {}
                    for symbol in valid_symbols:
                        ticker = await self.fetch_ticker(symbol)
                        if ticker:
                            tickers[symbol] = ticker
            
            # Filter valid tickers
            valid_tickers = {}
            for symbol, ticker in tickers.items():
                if ticker and ticker.get('bid') and ticker.get('ask'):
                    valid_tickers[symbol] = ticker
            
            return valid_tickers
            
        except Exception as e:
            logger.error(f"Error fetching tickers from {self.name}: {e}")
            return {}
    
    async def fetch_orderbook(
        self,
        symbol: str,
        limit: int = 20
    ) -> Optional[Dict]:
        """
        Fetch orderbook with caching
        
        Args:
            symbol: Trading pair
            limit: Number of orders to fetch
        
        Returns:
            Orderbook dict with 'bids' and 'asks'
        """
        try:
            symbol = Validators.validate_symbol(symbol)
        except ValidationError as e:
            logger.warning(f"Invalid symbol: {e}")
            return None
        
        if symbol not in self.symbols:
            return None
        
        cache_key = f"{self.name}_{symbol}_orderbook_{limit}"
        
        async def _fetch():
            await self.rate_limiter.acquire()
            return await self.exchange.fetch_order_book(symbol, limit)
        
        try:
            orderbook = await self.orderbook_cache.get_or_fetch(cache_key, _fetch)
            return Validators.validate_orderbook(orderbook)
        except Exception as e:
            logger.error(f"Error fetching orderbook {symbol} from {self.name}: {e}")
            return None
    
    async def fetch_orderbooks_batch(
        self,
        symbols: List[str],
        limit: int = 20
    ) -> Dict[str, Dict]:
        """
        Fetch multiple orderbooks in parallel
        
        Args:
            symbols: List of symbols
            limit: Orderbook depth
        
        Returns:
            Dict {symbol: orderbook}
        """
        tasks = []
        valid_symbols = []
        
        for symbol in symbols:
            try:
                symbol = Validators.validate_symbol(symbol)
                if symbol in self.symbols:
                    valid_symbols.append(symbol)
                    tasks.append(self.fetch_orderbook(symbol, limit))
            except ValidationError:
                continue
        
        if not tasks:
            return {}
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        orderbooks = {}
        for symbol, result in zip(valid_symbols, results):
            if result and not isinstance(result, Exception):
                orderbooks[symbol] = result
        
        return orderbooks
    
    async def fetch_balance(self) -> Dict[str, float]:
        """
        Fetch account balance
        
        Returns:
            Dict {currency: free_balance}
        """
        try:
            await self.rate_limiter.acquire()
            balance = await async_retry(
                lambda: self.exchange.fetch_balance(),
                max_attempts=3
            )
            
            # Extract free balances
            free_balance = {}
            if 'free' in balance:
                for currency, amount in balance['free'].items():
                    if amount and amount > 0:
                        free_balance[currency] = float(amount)
            
            return Validators.validate_balance(free_balance)
            
        except Exception as e:
            logger.error(f"Error fetching balance from {self.name}: {e}")
            return {}
    
    async def fetch_trading_fees(self) -> Dict[str, float]:
        """
        Get trading fees for markets
        
        Returns:
            Dict {symbol: fee_rate}
        """
        fees = {}
        
        try:
            # Get fees from markets data
            for symbol, market in self.markets.items():
                maker = market.get('maker', 0.001)
                taker = market.get('taker', 0.001)
                # Use average of maker/taker
                fees[symbol] = (maker + taker) / 2
            
            return fees
            
        except Exception as e:
            logger.error(f"Error fetching fees from {self.name}: {e}")
            # Return default fees
            return {symbol: 0.001 for symbol in self.symbols}
    
    async def get_withdrawal_fee(self, currency: str) -> Dict[str, float]:
        """
        Get withdrawal fee for currency
        
        Args:
            currency: Currency code (e.g., 'BTC')
        
        Returns:
            Dict with 'fee' and 'percentage'
        """
        try:
            currency = currency.upper()
            
            if currency in self.exchange.currencies:
                info = self.exchange.currencies[currency]
                
                # Try to get fee info
                fee_info = info.get('fee', info.get('withdraw', {}))
                
                if isinstance(fee_info, dict):
                    fee = fee_info.get('fee', 0)
                elif isinstance(fee_info, (int, float)):
                    fee = fee_info
                else:
                    fee = 0
                
                return {
                    'fee': float(fee),
                    'percentage': 0.0  # Most exchanges use flat fees
                }
            
            return {'fee': 0.0, 'percentage': 0.0}
            
        except Exception as e:
            logger.warning(f"Error getting withdrawal fee for {currency}: {e}")
            return {'fee': 0.0, 'percentage': 0.0}
    
    async def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: Optional[float] = None
    ) -> Optional[Dict]:
        """
        Create order (market or limit)
        
        Args:
            symbol: Trading pair
            side: 'buy' or 'sell'
            order_type: 'market' or 'limit'
            amount: Order amount
            price: Price for limit orders
        
        Returns:
            Order info dict or None on error
        """
        try:
            # Validate inputs
            symbol = Validators.validate_symbol(symbol)
            amount = Validators.validate_amount(amount)
            
            if side not in ['buy', 'sell']:
                raise ValidationError(f"Invalid side: {side}")
            
            if order_type not in ['market', 'limit']:
                raise ValidationError(f"Invalid order type: {order_type}")
            
            if order_type == 'limit':
                if price is None:
                    raise ValidationError("Price required for limit orders")
                price = Validators.validate_price(price)
            
            # Create order
            await self.rate_limiter.acquire()
            
            if order_type == 'market':
                order = await self.exchange.create_market_order(
                    symbol, side, amount
                )
            else:
                order = await self.exchange.create_limit_order(
                    symbol, side, amount, price
                )
            
            logger.info(
                f"📝 Order created on {self.name}: {side} {amount} {symbol} "
                f"@ {price if price else 'market'}"
            )
            
            return order
            
        except Exception as e:
            logger.error(f"Error creating order on {self.name}: {e}")
            return None
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        Cancel order
        
        Args:
            order_id: Order ID
            symbol: Trading pair
        
        Returns:
            True if cancelled successfully
        """
        try:
            await self.rate_limiter.acquire()
            await self.exchange.cancel_order(order_id, symbol)
            logger.info(f"❌ Order {order_id} cancelled on {self.name}")
            return True
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    async def fetch_order_status(self, order_id: str, symbol: str) -> Optional[str]:
        """
        Get order status
        
        Args:
            order_id: Order ID
            symbol: Trading pair
        
        Returns:
            Status string ('open', 'closed', 'canceled') or None
        """
        try:
            await self.rate_limiter.acquire()
            order = await self.exchange.fetch_order(order_id, symbol)
            return order.get('status')
        except Exception as e:
            logger.error(f"Error fetching order status: {e}")
            return None
    
    async def test_connection(self) -> bool:
        """
        Test exchange connection
        
        Returns:
            True if connection OK
        """
        try:
            if not self._initialized:
                await self.initialize()
            
            # Try to fetch a ticker
            await self.rate_limiter.acquire()
            await self.exchange.fetch_status()
            
            logger.info(f"✅ {self.name.upper()} connection OK")
            return True
            
        except Exception as e:
            logger.error(f"❌ {self.name.upper()} connection failed: {e}")
            return False
    
    async def close(self):
        """Close exchange connection"""
        if self.exchange:
            await self.exchange.close()
            logger.info(f"🔌 {self.name.upper()} connection closed")
    
    def __repr__(self):
        return f"ExchangeConnector({self.name}, {len(self.symbols)} symbols)"


class MultiExchangeConnector:
    """
    Manager for multiple exchanges
    Handles parallel operations across exchanges
    """
    
    def __init__(self, config: Dict):
        """
        Initialize multi-exchange connector
        
        Args:
            config: Full config dict with 'exchanges' section
        """
        self.config = config
        self.exchanges: Dict[str, ExchangeConnector] = {}
        self._initialized = False
        
        logger.info("🌐 MultiExchangeConnector initialized")
    
    async def initialize(self):
        """Initialize all enabled exchanges"""
        if self._initialized:
            return
        
        exchanges_config = self.config.get('exchanges', {})
        
        for exc_name, exc_config in exchanges_config.items():
            if not exc_config.get('enabled', False):
                logger.info(f"⏭️  {exc_name.upper()} disabled in config")
                continue
            
            try:
                connector = ExchangeConnector(exc_name, exc_config)
                await connector.initialize()
                self.exchanges[exc_name] = connector
            except Exception as e:
                logger.error(f"Failed to initialize {exc_name}: {e}")
        
        self._initialized = True
        logger.info(f"✅ Initialized {len(self.exchanges)} exchanges")
    
    async def fetch_all_tickers(self) -> Dict[str, Dict[str, Dict]]:
        """
        Fetch tickers from all exchanges in parallel
        
        Returns:
            Dict {exchange_name: {symbol: ticker}}
        """
        tasks = {
            name: connector.fetch_tickers()
            for name, connector in self.exchanges.items()
        }
        
        results = await asyncio.gather(
            *tasks.values(),
            return_exceptions=True
        )
        
        all_tickers = {}
        for name, result in zip(tasks.keys(), results):
            if result and not isinstance(result, Exception):
                all_tickers[name] = result
            else:
                all_tickers[name] = {}
        
        return all_tickers
    
    async def fetch_all_balances(self) -> Dict[str, Dict[str, float]]:
        """
        Fetch balances from all exchanges
        
        Returns:
            Dict {exchange_name: {currency: amount}}
        """
        tasks = {
            name: connector.fetch_balance()
            for name, connector in self.exchanges.items()
        }
        
        results = await asyncio.gather(
            *tasks.values(),
            return_exceptions=True
        )
        
        all_balances = {}
        for name, result in zip(tasks.keys(), results):
            if result and not isinstance(result, Exception):
                all_balances[name] = result
            else:
                all_balances[name] = {}
        
        return all_balances
    
    async def test_all_connections(self) -> Dict[str, bool]:
        """
        Test connections to all exchanges
        
        Returns:
            Dict {exchange_name: success}
        """
        tasks = {
            name: connector.test_connection()
            for name, connector in self.exchanges.items()
        }
        
        results = await asyncio.gather(*tasks.values())
        return dict(zip(tasks.keys(), results))
    
    def get_exchange(self, name: str) -> Optional[ExchangeConnector]:
        """Get exchange connector by name"""
        return self.exchanges.get(name)
    
    async def close_all(self):
        """Close all exchange connections"""
        await asyncio.gather(*[
            connector.close()
            for connector in self.exchanges.values()
        ])
        logger.info("🔌 All exchange connections closed")