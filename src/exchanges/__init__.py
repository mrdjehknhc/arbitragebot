"""
Exchange integration with async support
Backward compatible with sync code
"""
import ccxt
import asyncio
import os
from typing import Dict, Optional
from ..utils.logger import get_logger

logger = get_logger()

class ExchangeManager:
    """
    Exchange manager with both sync and async support
    Backward compatible with existing code
    """
    
    SUPPORTED_EXCHANGES = ['bybit', 'binance', 'okx', 'kucoin', 'gateio']
    
    def __init__(self, config: Dict):
        self.config = config
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self._init_exchanges()
    
    def _init_exchanges(self):
        """Initialize exchanges (sync version)"""
        exchanges_config = self.config.get('exchanges', {})
        
        for exc_name in self.SUPPORTED_EXCHANGES:
            exc_conf = exchanges_config.get(exc_name, {})
            
            if not exc_conf.get('enabled', False):
                logger.info(f"Exchange {exc_name} is disabled in config")
                continue
            
            try:
                # ✅ FIX: Читаем ключи из ENV ПЕРЕД созданием
                api_key = os.getenv(exc_conf.get('api_key_env', ''), '')
                api_secret = os.getenv(exc_conf.get('api_secret_env', ''), '')
                passphrase = os.getenv(exc_conf.get('passphrase_env', ''), '')
                
                # Добавляем в конфиг
                exc_conf['api_key'] = api_key
                exc_conf['api_secret'] = api_secret
                if passphrase:
                    exc_conf['passphrase'] = passphrase
                
                exchange = self._create_exchange(exc_name, exc_conf)
                if exchange:
                    self.exchanges[exc_name] = exchange
                    logger.info(f"✅ {exc_name.upper()} initialized successfully")
            except Exception as e:
                logger.error(f"❌ Failed to initialize {exc_name}: {e}")
    
    def _create_exchange(self, name: str, config: Dict) -> Optional[ccxt.Exchange]:
        """Create CCXT exchange instance"""
        api_key = config.get('api_key', '')
        api_secret = config.get('api_secret', '')
        testnet = config.get('testnet', False)
        
        # Base params
        params = {
            'enableRateLimit': True,
            'timeout': 30000,
            'options': {'defaultType': 'spot'}
        }
        
        # API keys (if available)
        if api_key and api_secret:
            params['apiKey'] = api_key
            params['secret'] = api_secret
            logger.info(f"🔑 {name.upper()}: API keys loaded")
        else:
            logger.warning(f"⚠️ {name.upper()}: No API keys (read-only mode)")
        
        # Create exchange
        if name == 'bybit':
            exchange = ccxt.bybit(params)
            if testnet:
                exchange.set_sandbox_mode(True)
        
        elif name == 'binance':
            exchange = ccxt.binance(params)
            if testnet:
                exchange.set_sandbox_mode(True)
        
        elif name == 'okx':
            passphrase = config.get('passphrase', '')
            if passphrase:
                params['password'] = passphrase
            exchange = ccxt.okx(params)
            if testnet:
                exchange.set_sandbox_mode(True)
        
        elif name == 'kucoin':
            passphrase = config.get('passphrase', '')
            if passphrase:
                params['password'] = passphrase
            exchange = ccxt.kucoin(params)
            if testnet:
                exchange.set_sandbox_mode(True)
        
        elif name == 'gateio':
            exchange = ccxt.gateio(params)
            if testnet:
                exchange.set_sandbox_mode(True)
        
        else:
            logger.error(f"Unknown exchange: {name}")
            return None
        
        return exchange
    
    def get_exchange(self, name: str) -> Optional[ccxt.Exchange]:
        """Get exchange instance"""
        return self.exchanges.get(name)
    
    def get_all_exchanges(self) -> Dict[str, ccxt.Exchange]:
        """Get all active exchanges"""
        return self.exchanges
    
    def test_connections(self) -> Dict[str, bool]:
        """Test connections to all exchanges"""
        results = {}
        
        for name, exchange in self.exchanges.items():
            try:
                exchange.load_markets()
                balance = exchange.fetch_balance()
                results[name] = True
                logger.info(f"✅ {name.upper()} connection: OK")
            except Exception as e:
                results[name] = False
                logger.error(f"❌ {name.upper()} connection failed: {e}")
        
        return results
    
    def get_balances(self) -> Dict[str, Dict]:
        """Get balances from all exchanges (sync)"""
        balances = {}
        
        for name, exchange in self.exchanges.items():
            try:
                balance = exchange.fetch_balance()
                balances[name] = {
                    k: v for k, v in balance['free'].items() 
                    if v and v > 0
                }
                logger.debug(f"Fetched balance from {name}: {len(balances[name])} currencies")
            except Exception as e:
                logger.error(f"Failed to fetch balance from {name}: {e}")
                balances[name] = {}
        
        return balances
    
    async def get_balances_async(self) -> Dict[str, Dict]:
        """Get balances from all exchanges (async version)"""
        try:
            from ..services.exchange_connector import MultiExchangeConnector
            
            async_connector = MultiExchangeConnector(self.config)
            await async_connector.initialize()
            
            balances = await async_connector.fetch_all_balances()
            
            await async_connector.close_all()
            
            return balances
            
        except Exception as e:
            logger.error(f"Error in async balance fetch: {e}")
            return self.get_balances()
    
    def get_trading_fees(self) -> Dict[str, float]:
        """Get trading fees"""
        fees = {}
        
        default_fees = {
            'bybit': 0.001,
            'binance': 0.001,
            'okx': 0.0008,
            'kucoin': 0.001,
            'gateio': 0.002
        }
        
        for name, exchange in self.exchanges.items():
            try:
                markets = exchange.load_markets()
                if markets:
                    sample_market = list(markets.values())[0]
                    maker = sample_market.get('maker', default_fees[name])
                    taker = sample_market.get('taker', default_fees[name])
                    fees[name] = (maker + taker) / 2
                else:
                    fees[name] = default_fees[name]
            except Exception as e:
                logger.warning(f"Using default fee for {name}: {e}")
                fees[name] = default_fees.get(name, 0.001)
        
        return fees

def create_exchange_manager(config: Dict) -> ExchangeManager:
    """Factory function"""
    return ExchangeManager(config)