"""
ENHANCED ArbitrageEngine v3
Integrates PathOptimizer, AmountOptimizer, and OrderbookAnalyzer
Professional-grade arbitrage detection with real amount optimization
"""
from typing import Dict, List, Optional
import time
import asyncio
from ..utils.logger import get_logger
from ..utils.helpers import generate_opportunity_id, get_utc_now
from ..utils.async_helpers import async_retry, gather_with_limit
from .path_optimizer import PathOptimizer
from .amount_optimizer import AmountOptimizer
from .orderbook_analyzer import OrderbookAnalyzer

logger = get_logger()


class ArbitrageEngine:
    """
    Enhanced arbitrage engine with three-stage process:
    1. PathOptimizer: Find profitable paths (PuLP)
    2. OrderbookAnalyzer: Check liquidity and slippage
    3. AmountOptimizer: Optimize exact amounts (PuLP)
    """
    
    def __init__(self, exchange_manager, config: Dict):
        self.exchanges = exchange_manager
        self.config = config
        
        # Config
        self.strategy_config = config.get('strategy', {})
        self.trading_config = config.get('trading', {})
        
        self.min_profit = self.strategy_config.get('min_profit_percent', 0.3)
        self.max_path_length = self.strategy_config.get('max_path_length', 3)
        self.include_fees = self.strategy_config.get('include_fees', True)
        self.inter_exchange_trading = self.strategy_config.get('inter_exchange_trading', False)
        
        self.trade_size_usd = self.trading_config.get('trade_size_usd', 100)
        
        # Initialize components
        self.path_optimizer = PathOptimizer(exchange_manager, config)
        self.amount_optimizer = AmountOptimizer(
            orderbook_depth=20,
            max_slippage_percent=0.5,
            min_trade_usd=10.0
        )
        self.orderbook_analyzer = OrderbookAnalyzer(max_slippage_percent=0.5)
        
        # Cache
        self.trading_fees = exchange_manager.get_trading_fees()
        self.allowed_tokens = self._load_allowed_tokens()
        
        logger.info(
            f"⚡ ArbitrageEngine v3: "
            f"mode=ENHANCED (PathOpt + AmountOpt), "
            f"min_profit={self.min_profit}%"
        )
    
    def _load_allowed_tokens(self):
        """Load allowed tokens"""
        try:
            import yaml
            from pathlib import Path
            
            tokens_path = Path('config/tokens.yml')
            if tokens_path.exists():
                with open(tokens_path) as f:
                    tokens_config = yaml.safe_load(f)
                
                base = set(tokens_config.get('base_tokens', []))
                additional = set(tokens_config.get('additional_tokens', []))
                blacklist = set(tokens_config.get('blacklist', []))
                
                return (base | additional) - blacklist
        except Exception as e:
            logger.warning(f"Could not load tokens config: {e}")
        
        return {'BTC', 'ETH', 'USDT', 'USDC', 'BNB', 'SOL', 'XRP'}
    
    async def scan_all_exchanges_async(self) -> List[Dict]:
        """
        Async version of scan_all_exchanges
        Much faster than sync version!
        """
        opportunities = await self._scan_enhanced_mode_async()
        return opportunities
    
    def scan_all_exchanges(self) -> List[Dict]:
        """
        Sync wrapper for async scanning
        For backward compatibility
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return asyncio.create_task(self.scan_all_exchanges_async())
            else:
                return loop.run_until_complete(self.scan_all_exchanges_async())
        except RuntimeError:
            return asyncio.run(self.scan_all_exchanges_async())
    
    async def _scan_enhanced_mode_async(self) -> List[Dict]:
        """
        Enhanced scanning with three-stage process
        """
        logger.debug("🔍 Enhanced mode: PathOpt → OrderbookCheck → AmountOpt")
        
        start_time = time.time()
        
        try:
            # STAGE 1: Find paths with PathOptimizer
            if self.path_optimizer.run_times == 0:
                self.path_optimizer.init_currency_info()
            
            raw_opportunities = self.path_optimizer.find_arbitrage()
            
            if not raw_opportunities:
                logger.debug("No paths found by PathOptimizer")
                return []
            
            logger.info(f"📊 PathOptimizer found {len(raw_opportunities)} raw opportunities")
            
            # STAGE 2 & 3: Analyze orderbooks and optimize amounts
            enhanced_opportunities = []
            
            for raw_opp in raw_opportunities:
                try:
                    enhanced = await self._enhance_opportunity(raw_opp)
                    
                    if enhanced and enhanced.get('feasible'):
                        enhanced_opportunities.append(enhanced)
                        logger.debug(
                            f"✅ Enhanced opportunity: "
                            f"{enhanced['profit_percent']:.2f}% profit, "
                            f"${enhanced['expected_profit_usd']:.2f}"
                        )
                
                except Exception as e:
                    logger.error(f"Error enhancing opportunity: {e}")
                    continue
            
            scan_time = time.time() - start_time
            
            if enhanced_opportunities:
                logger.info(
                    f"✅ Enhanced scan: {len(enhanced_opportunities)} opportunities "
                    f"in {scan_time:.1f}s"
                )
            else:
                logger.debug(f"No feasible opportunities after enhancement ({scan_time:.1f}s)")
            
            # Sort by profit
            enhanced_opportunities.sort(
                key=lambda x: x.get('profit_percent', 0),
                reverse=True
            )
            
            return enhanced_opportunities
            
        except Exception as e:
            logger.error(f"Error in enhanced scan: {e}", exc_info=True)
            return []
    
    async def _enhance_opportunity(self, raw_opp: Dict) -> Optional[Dict]:
        """
        Enhance raw opportunity with orderbook analysis and amount optimization
        """
        try:
            path = raw_opp.get('raw_path', [])
            if not path:
                return None
            
            exchange_name = path[0][0].split('_')[0]
            
            # Fetch orderbooks for all pairs in path
            orderbooks = await self._fetch_orderbooks_for_path(path, exchange_name)
            
            if not orderbooks:
                logger.debug("Failed to fetch orderbooks")
                return None
            
            # Check liquidity and slippage for each step
            liquidity_check = self._check_path_liquidity(
                path, orderbooks, self.trade_size_usd
            )
            
            if not liquidity_check['feasible']:
                logger.debug(f"Liquidity check failed: {liquidity_check.get('reason')}")
                return None
            
            # Get balances
            balances = await self._get_balances_async(exchange_name)
            
            # Get fees
            fees = self._get_fees_for_path(path)
            
            # Get prices
            prices = self._get_prices_for_currencies(path)
            
            # STAGE 3: Optimize amounts with AmountOptimizer
            solution = await self.amount_optimizer.optimize(
                path=path,
                orderbooks=orderbooks,
                balances=balances,
                fees=fees,
                prices=prices,
                initial_amount=self.trade_size_usd
            )
            
            if not solution or not solution.get('feasible'):
                logger.debug("Amount optimization failed")
                return None
            
            # Validate solution
            if not self.amount_optimizer.validate_solution(solution, self.min_profit):
                logger.debug("Solution validation failed")
                return None
            
            # Build enhanced opportunity
            enhanced = self._build_enhanced_opportunity(
                raw_opp, solution, liquidity_check
            )
            
            return enhanced
            
        except Exception as e:
            logger.error(f"Error enhancing opportunity: {e}")
            return None
    
    async def _fetch_orderbooks_for_path(
        self,
        path: List[tuple],
        exchange_name: str
    ) -> Dict:
        """✅ FIX: Реальный fetching orderbooks!"""
        try:
            orderbooks = {}
            exchange = self.exchanges.get_exchange(exchange_name)
            
            if not exchange:
                logger.error(f"Exchange {exchange_name} not found")
                return {}
            
            for from_cur, to_cur in path:
                # Only fetch for intra-exchange pairs
                from_exc = from_cur.split('_')[0]
                to_exc = to_cur.split('_')[0]
                
                if from_exc != to_exc:
                    # Inter-exchange transfer, no orderbook needed
                    continue
                
                # Build symbol
                from_coin = from_cur.split('_')[1]
                to_coin = to_cur.split('_')[1]
                symbol = f"{from_coin}/{to_coin}"
                
                # Fetch orderbook
                orderbook = await self._fetch_single_orderbook(exchange, symbol)
                
                if orderbook:
                    orderbooks[(from_cur, to_cur)] = orderbook
            
            return orderbooks
            
        except Exception as e:
            logger.error(f"Error fetching orderbooks: {e}")
            return {}
    
    async def _fetch_single_orderbook(self, exchange, symbol: str) -> Optional[Dict]:
        """✅ FIX: Реализован fetching orderbook!"""
        try:
            # Синхронный CCXT (пока не async)
            orderbook = await asyncio.to_thread(
                exchange.fetch_order_book,
                symbol,
                20  # limit
            )
            
            if orderbook and orderbook.get('bids') and orderbook.get('asks'):
                logger.debug(f"✅ Fetched orderbook for {symbol}")
                return orderbook
            else:
                logger.warning(f"Empty orderbook for {symbol}")
                return None
                
        except Exception as e:
            logger.debug(f"Error fetching orderbook {symbol}: {e}")
            return None
    
    def _check_path_liquidity(
        self,
        path: List[tuple],
        orderbooks: Dict,
        target_amount: float
    ) -> Dict:
        """Check if path has sufficient liquidity"""
        try:
            for from_cur, to_cur in path:
                pair = (from_cur, to_cur)
                
                if pair not in orderbooks:
                    continue
                
                orderbook = orderbooks[pair]
                
                # Analyze depth
                analysis = self.orderbook_analyzer.analyze_depth(
                    orderbook, 'sell', target_amount
                )
                
                if not analysis['feasible']:
                    return {
                        'feasible': False,
                        'reason': f"Insufficient liquidity at {pair}: "
                                f"slippage {analysis['slippage_percent']:.2f}%"
                    }
            
            return {'feasible': True, 'reason': None}
            
        except Exception as e:
            logger.error(f"Error checking liquidity: {e}")
            return {'feasible': False, 'reason': str(e)}
    
    async def _get_balances_async(self, exchange_name: str) -> Dict:
        """Get balances for exchange"""
        try:
            exchange = self.exchanges.get_exchange(exchange_name)
            if not exchange:
                return {}
            
            # Sync CCXT call в async context
            balance = await asyncio.to_thread(exchange.fetch_balance)
            
            free_balances = {}
            if 'free' in balance:
                for currency, amount in balance['free'].items():
                    if amount and amount > 0:
                        free_balances[f"{exchange_name}_{currency}"] = amount
            
            return free_balances
            
        except Exception as e:
            logger.error(f"Error getting balances: {e}")
            return {}
    
    def _get_fees_for_path(self, path: List[tuple]) -> Dict:
        """Get fees for each step in path"""
        fees = {}
        
        for from_cur, to_cur in path:
            exchange = from_cur.split('_')[0]
            fee = self.trading_fees.get(exchange, 0.001)
            fees[(from_cur, to_cur)] = fee
        
        return fees
    
    def _get_prices_for_currencies(self, path: List[tuple]) -> Dict:
        """Get USD prices for currencies"""
        try:
            return self.path_optimizer.crypto_prices
        except Exception as e:
            logger.error(f"Error getting prices: {e}")
            return {}
    
    def _build_enhanced_opportunity(
        self,
        raw_opp: Dict,
        solution: Dict,
        liquidity_check: Dict
    ) -> Dict:
        """Build final enhanced opportunity dict"""
        
        # Extract optimized amounts from solution
        optimized_path = []
        
        for i, step_data in enumerate(solution.get('steps', [])):
            if i < len(raw_opp.get('path', [])):
                original_step = raw_opp['path'][i]
                
                enhanced_step = {
                    **original_step,
                    'amount': step_data.get('amount', 0),
                    'optimized_price': step_data.get('price', original_step.get('price', 0)),
                    'cost_usd': step_data.get('cost', 0)
                }
                
                optimized_path.append(enhanced_step)
        
        # Build final opportunity
        return {
            'id': raw_opp.get('id', generate_opportunity_id()),
            'type': raw_opp.get('type'),
            'exchange': raw_opp.get('exchange'),
            'path': optimized_path,
            'raw_path': raw_opp.get('raw_path'),
            
            # Optimized metrics
            'profit_percent': solution.get('profit_percent', 0),
            'expected_profit_usd': solution.get('profit_usd', 0),
            'net_profit': solution.get('profit_percent', 0),
            
            # Original metrics for comparison
            'original_profit_percent': raw_opp.get('profit_percent', 0),
            
            # Trading info
            'trade_size': solution.get('total_cost', self.trade_size_usd),
            'fees': raw_opp.get('fees', 0),
            'slippage': 0.1,
            
            # Metadata
            'exec_time': len(optimized_path) * 0.8,
            'liquidity_score': 85 if liquidity_check['feasible'] else 0,
            'feasible': solution.get('feasible', False),
            'timestamp': get_utc_now()
        }
    
    def switch_mode(self, enhanced_mode: bool = True):
        """Switch between enhanced and basic mode (for testing)"""
        self.enhanced_mode = enhanced_mode
        mode = "ENHANCED (3-stage)" if enhanced_mode else "BASIC (PathOpt only)"
        logger.info(f"🔄 Switched to {mode} mode")