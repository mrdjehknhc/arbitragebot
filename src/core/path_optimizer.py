"""
PRODUCTION PathOptimizer with PuLP (FREE!) - DIVERSITY FIX
Graph-based arbitrage path optimization using linear programming
"""
import numpy as np
from pulp import *
from itertools import combinations
from typing import Dict, List, Optional, Set, Tuple
import time
import random
from ..utils.logger import get_logger
from ..utils.helpers import generate_opportunity_id, get_utc_now

logger = get_logger()


class PathOptimizer:
    """
    Advanced path optimizer using PuLP linear programming (FREE!)
    ✅ FIX: Added path diversity to find different opportunities
    """
    
    def __init__(self, exchange_manager, config: Dict):
        self.exchanges = exchange_manager
        self.config = config
        
        strategy_config = config.get('strategy', {})
        self.path_length = strategy_config.get('max_path_length', 4)
        self.min_profit = strategy_config.get('min_profit_percent', 0.3)
        self.include_fees = strategy_config.get('include_fees', True)
        self.inter_exchange_trading = strategy_config.get('inter_exchange_trading', False)
        
        trading_config = config.get('trading', {})
        self.trade_size_usd = trading_config.get('trade_size_usd', 100)
        self.min_trading_limit = trading_config.get('min_trading_limit', 10)
        
        # Internal state
        self.currency_set: Set[str] = set()
        self.currency2index: Dict[str, int] = {}
        self.index2currency: Dict[int, str] = {}
        self.length: int = 0
        
        # Matrices
        self.transit_price_matrix: Optional[np.ndarray] = None
        self.commission_matrix: Optional[np.ndarray] = None
        self.vol_matrix: Optional[np.ndarray] = None
        self.var_location: Optional[np.ndarray] = None
        
        # Solution
        self.path: List[Tuple[str, str]] = []
        self.profit_percent: float = 0.0
        self.x: Optional[np.ndarray] = None
        self.xs: Optional[np.ndarray] = None
        
        # Cache
        self.trading_fees = exchange_manager.get_trading_fees()
        self.withdrawal_fees: Dict = {}
        self.balance_dict: Dict = {}
        self.price_data: Dict = {}
        self.crypto_prices: Dict = {}
        
        # Allowed tokens
        self.allowed_tokens = self._load_allowed_tokens()
        
        # Run counter
        self.run_times = 0
        self.refresh_interval = 100
        
        # ✅ FIX: Path diversity
        self.found_paths: List[List[Tuple]] = []  # Store found paths
        self.path_block_time = 60  # Block path for 60 seconds
        self.last_path_time: Dict = {}  # Track when path was found
        
        logger.info(f"⚡ PathOptimizer (PuLP): path_length={self.path_length}, min_profit={self.min_profit}%")
    
    def _load_allowed_tokens(self) -> Set[str]:
        """Load allowed tokens from config"""
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
        
        return {'BTC', 'ETH', 'USDT', 'USDC', 'BNB', 'SOL', 'XRP', 'ADA'}
    
    def init_currency_info(self):
        """Initialize currency set and mappings"""
        logger.info("🔄 Initializing currency info...")
        
        self.currency_set.clear()
        
        for exc_name, exchange in self.exchanges.get_all_exchanges().items():
            try:
                markets = exchange.load_markets()
                
                for currency in exchange.currencies.keys():
                    if currency in self.allowed_tokens:
                        full_name = f"{exc_name}_{currency}"
                        self.currency_set.add(full_name)
                
            except Exception as e:
                logger.error(f"Failed to load markets for {exc_name}: {e}")
        
        self.length = len(self.currency_set)
        self.currency2index = {cur: i for i, cur in enumerate(sorted(self.currency_set))}
        self.index2currency = {i: cur for cur, i in self.currency2index.items()}
        
        logger.info(f"✅ Initialized {self.length} currencies across {len(self.exchanges.get_all_exchanges())} exchanges")
    
    def find_arbitrage(self) -> List[Dict]:
        """Main function to find arbitrage opportunities"""
        if self.run_times == 0:
            self._first_run_init()
        
        if self.run_times % self.refresh_interval == 0:
            self._update_fees_and_prices()
        
        self._update_balances()
        self._update_prices()
        self._update_volumes()
        
        # ✅ FIX: Clean old blocked paths
        self._clean_blocked_paths()
        
        opportunities = self._solve_pulp()
        
        self.run_times += 1
        
        return opportunities
    
    def _clean_blocked_paths(self):
        """Remove paths that have been blocked for too long"""
        current_time = time.time()
        paths_to_remove = []
        
        for path_key, block_time in self.last_path_time.items():
            if current_time - block_time > self.path_block_time:
                paths_to_remove.append(path_key)
        
        for path_key in paths_to_remove:
            del self.last_path_time[path_key]
    
    def _is_path_blocked(self, path: List[Tuple]) -> bool:
        """Check if path is currently blocked"""
        path_key = tuple(sorted(path))
        
        if path_key in self.last_path_time:
            current_time = time.time()
            if current_time - self.last_path_time[path_key] < self.path_block_time:
                return True
        
        return False
    
    def _block_path(self, path: List[Tuple]):
        """Block path temporarily"""
        path_key = tuple(sorted(path))
        self.last_path_time[path_key] = time.time()
    
    def _first_run_init(self):
        """Initialize on first run"""
        logger.info("🔧 First run initialization...")
        
        if self.length == 0:
            self.init_currency_info()
        
        self._get_var_location()
        self._update_fees_and_prices()
        
        logger.info("✅ First run init complete")
    
    def _update_fees_and_prices(self):
        """Update fees and prices"""
        logger.debug("Updating fees and prices...")
        
        if self.inter_exchange_trading:
            self.withdrawal_fees = self._fetch_withdrawal_fees()
        
        self.crypto_prices = self._fetch_crypto_prices()
        self._build_commission_matrix()
    
    def _fetch_withdrawal_fees(self) -> Dict:
        """Fetch withdrawal fees"""
        fees = {}
        
        for exc_name, exchange in self.exchanges.get_all_exchanges().items():
            try:
                currencies = exchange.currencies
                
                for currency, info in currencies.items():
                    if currency in self.allowed_tokens:
                        full_name = f"{exc_name}_{currency}"
                        
                        fee_info = info.get('fee', info.get('withdraw', {}))
                        if isinstance(fee_info, dict):
                            coin_fee = fee_info.get('fee', 0)
                        else:
                            coin_fee = fee_info if fee_info else 0
                        
                        price = self.crypto_prices.get(currency, {}).get('price', 0)
                        usd_fee = coin_fee * price if price else 0
                        
                        fees[full_name] = {
                            'coin_fee': coin_fee,
                            'usd_fee': usd_fee,
                            'usd_rate': usd_fee / self.trade_size_usd if self.trade_size_usd else 0
                        }
                        
            except Exception as e:
                logger.warning(f"Failed to fetch withdrawal fees for {exc_name}: {e}")
        
        return fees
    
    def _fetch_crypto_prices(self) -> Dict:
        """Fetch crypto prices in USD"""
        prices = {}
        
        for exc_name, exchange in self.exchanges.get_all_exchanges().items():
            try:
                tickers = exchange.fetch_tickers()
                
                for symbol, ticker in tickers.items():
                    if '/' not in symbol:
                        continue
                    
                    base, quote = symbol.split('/')
                    
                    if quote in ['USDT', 'USDC'] and base in self.allowed_tokens:
                        if base not in prices:
                            prices[base] = {
                                'price': ticker.get('bid', 0),
                                'last': ticker.get('last', 0)
                            }
                
            except Exception as e:
                logger.warning(f"Failed to fetch prices from {exc_name}: {e}")
        
        for stable in ['USDT', 'USDC', 'BUSD', 'DAI']:
            if stable not in prices:
                prices[stable] = {'price': 1.0, 'last': 1.0}
        
        return prices
    
    def _build_commission_matrix(self):
        """Build commission matrix"""
        self.commission_matrix = np.zeros([self.length, self.length])
        
        for exc_name, fee in self.trading_fees.items():
            indices = [
                idx for cur, idx in self.currency2index.items() 
                if cur.startswith(f"{exc_name}_")
            ]
            
            if indices:
                self.commission_matrix[np.ix_(indices, indices)] = fee
        
        if self.inter_exchange_trading:
            for from_cur, to_cur in self._get_inter_exchange_pairs():
                from_idx = self.currency2index.get(from_cur)
                to_idx = self.currency2index.get(to_cur)
                
                if from_idx is not None and to_idx is not None:
                    fee_info = self.withdrawal_fees.get(from_cur, {})
                    self.commission_matrix[from_idx, to_idx] = fee_info.get('usd_rate', 0.01)
    
    def _get_inter_exchange_pairs(self) -> List[Tuple[str, str]]:
        """Get inter-exchange pairs"""
        pairs = []
        
        coin_map = {}
        for cur in self.currency_set:
            exc, coin = cur.split('_')
            if coin not in coin_map:
                coin_map[coin] = []
            coin_map[coin].append(cur)
        
        for coin, currencies in coin_map.items():
            if len(currencies) >= 2:
                for cur1, cur2 in combinations(currencies, 2):
                    pairs.append((cur1, cur2))
                    pairs.append((cur2, cur1))
        
        return pairs
    
    def _update_balances(self):
        """Update balances"""
        self.balance_dict.clear()
        
        try:
            balances = self.exchanges.get_balances()
            
            for exc_name, exc_balance in balances.items():
                for currency, amount in exc_balance.items():
                    if amount > 0 and currency in self.allowed_tokens:
                        full_name = f"{exc_name}_{currency}"
                        
                        price = self.crypto_prices.get(currency, {}).get('price', 0)
                        usd_value = amount * price if price else 0
                        
                        self.balance_dict[full_name] = {
                            'balance': amount,
                            'usd_balance': usd_value
                        }
                        
        except Exception as e:
            logger.warning(f"Failed to update balances: {e}")
    
    def _update_prices(self):
        """Update transit price matrix"""
        self.transit_price_matrix = np.zeros([self.length, self.length])
        self.price_data.clear()
        
        for exc_name, exchange in self.exchanges.get_all_exchanges().items():
            try:
                tickers = exchange.fetch_tickers()
                
                for symbol, ticker in tickers.items():
                    if '/' not in symbol:
                        continue
                    
                    base, quote = symbol.split('/')
                    
                    if base not in self.allowed_tokens or quote not in self.allowed_tokens:
                        continue
                    
                    from_cur = f"{exc_name}_{base}"
                    to_cur = f"{exc_name}_{quote}"
                    
                    if from_cur not in self.currency2index or to_cur not in self.currency2index:
                        continue
                    
                    from_idx = self.currency2index[from_cur]
                    to_idx = self.currency2index[to_cur]
                    
                    bid = ticker.get('bid', 0)
                    ask = ticker.get('ask', 0)
                    
                    if not bid or not ask or bid <= 0 or ask <= 0:
                        continue
                    
                    # ✅ FIX: Add small random noise for diversity (±0.01%)
                    noise_factor = 1.0 + random.uniform(-0.0001, 0.0001)
                    
                    self.transit_price_matrix[from_idx, to_idx] = bid * noise_factor
                    self.transit_price_matrix[to_idx, from_idx] = (1 / ask) * noise_factor
                    
                    self.price_data[f"{from_cur}/{to_cur}"] = {
                        'bid': bid,
                        'ask': ask,
                        'baseVolume': ticker.get('baseVolume', 0),
                        'quoteVolume': ticker.get('quoteVolume', 0)
                    }
                
            except Exception as e:
                logger.warning(f"Failed to update prices from {exc_name}: {e}")
        
        if self.inter_exchange_trading:
            for from_cur, to_cur in self._get_inter_exchange_pairs():
                from_idx = self.currency2index.get(from_cur)
                to_idx = self.currency2index.get(to_cur)
                
                if from_idx is not None and to_idx is not None:
                    if from_cur in self.withdrawal_fees:
                        self.transit_price_matrix[from_idx, to_idx] = 1
    
    def _update_volumes(self):
        """Update volume matrix"""
        self.vol_matrix = np.zeros([self.length, self.length])
        
        for pair, data in self.price_data.items():
            from_cur, to_cur = pair.split('/')
            
            if from_cur not in self.currency2index or to_cur not in self.currency2index:
                continue
            
            from_idx = self.currency2index[from_cur]
            to_idx = self.currency2index[to_cur]
            
            base_coin = from_cur.split('_')[-1]
            base_volume = data.get('baseVolume', 0)
            
            price = self.crypto_prices.get(base_coin, {}).get('price', 0)
            usd_volume = base_volume * price if price else 0
            
            feasible_volume = usd_volume * 0.01
            
            self.vol_matrix[from_idx, to_idx] = feasible_volume
            self.vol_matrix[to_idx, from_idx] = feasible_volume
        
        if self.inter_exchange_trading:
            for from_cur, to_cur in self._get_inter_exchange_pairs():
                from_idx = self.currency2index.get(from_cur)
                to_idx = self.currency2index.get(to_cur)
                
                if from_idx is not None and to_idx is not None:
                    from_balance = self.balance_dict.get(from_cur, {}).get('usd_balance', 0)
                    to_balance = self.balance_dict.get(to_cur, {}).get('usd_balance', 0)
                    
                    self.vol_matrix[from_idx, to_idx] = to_balance
                    self.vol_matrix[to_idx, from_idx] = from_balance
    
    def _get_var_location(self):
        """Get feasible trading pair locations"""
        self.var_location = np.zeros([self.length, self.length], dtype=bool)
        
        for exc_name, exchange in self.exchanges.get_all_exchanges().items():
            try:
                markets = exchange.load_markets()
                
                for symbol in markets.keys():
                    if '/' not in symbol:
                        continue
                    
                    base, quote = symbol.split('/')
                    
                    from_cur = f"{exc_name}_{base}"
                    to_cur = f"{exc_name}_{quote}"
                    
                    if from_cur in self.currency2index and to_cur in self.currency2index:
                        from_idx = self.currency2index[from_cur]
                        to_idx = self.currency2index[to_cur]
                        
                        self.var_location[from_idx, to_idx] = True
                        self.var_location[to_idx, from_idx] = True
                
            except Exception as e:
                logger.warning(f"Failed to get var locations for {exc_name}: {e}")
        
        if self.inter_exchange_trading:
            for from_cur, to_cur in self._get_inter_exchange_pairs():
                from_idx = self.currency2index.get(from_cur)
                to_idx = self.currency2index.get(to_cur)
                
                if from_idx is not None and to_idx is not None:
                    self.var_location[from_idx, to_idx] = True
    
    def _solve_pulp(self) -> List[Dict]:
        """Solve using PuLP with path diversity"""
        opportunities = []
        
        try:
            prob = LpProblem("Arbitrage", LpMaximize)
            
            x_vars = {}
            for i in range(self.length):
                for j in range(self.length):
                    if self.var_location[i, j]:
                        x_vars[(i, j)] = LpVariable(f"x_{i}_{j}", cat='Binary')
            
            if not x_vars:
                logger.debug("No feasible variables to optimize")
                return []
            
            # Build objective with random noise for diversity
            profit_matrix = np.zeros([self.length, self.length])
            
            for i in range(self.length):
                for j in range(self.length):
                    if self.var_location[i, j]:
                        price = self.transit_price_matrix[i, j]
                        fee = self.commission_matrix[i, j]
                        volume = self.vol_matrix[i, j]
                        
                        if price > 0 and volume >= self.min_trading_limit:
                            net_rate = price * (1 - fee)
                            
                            if net_rate > 0:
                                profit_matrix[i, j] = np.log(net_rate)
                            else:
                                profit_matrix[i, j] = -999
            
            obj_terms = []
            for (i, j), var in x_vars.items():
                obj_terms.append(profit_matrix[i, j] * var)
            
            prob += lpSum(obj_terms)
            
            # Constraints
            for i in range(self.length):
                in_vars = [x_vars[(j, i)] for j in range(self.length) if (j, i) in x_vars]
                out_vars = [x_vars[(i, j)] for j in range(self.length) if (i, j) in x_vars]
                
                if in_vars and out_vars:
                    prob += lpSum(in_vars) == lpSum(out_vars)
            
            for i in range(self.length):
                out_vars = [x_vars[(i, j)] for j in range(self.length) if (i, j) in x_vars]
                if out_vars:
                    prob += lpSum(out_vars) <= 1
            
            prob += lpSum(x_vars.values()) <= self.path_length
            prob += lpSum(x_vars.values()) >= 1
            
            if self.balance_dict:
                sufficient_indices = [
                    self.currency2index[cur]
                    for cur, info in self.balance_dict.items()
                    if info['usd_balance'] >= self.min_trading_limit
                ]
                
                if sufficient_indices:
                    start_vars = [
                        x_vars[(i, j)] 
                        for i in sufficient_indices 
                        for j in range(self.length) 
                        if (i, j) in x_vars
                    ]
                    if start_vars:
                        prob += lpSum(start_vars) >= 0.0001 * lpSum(x_vars.values())
            
            # Solve
            prob.solve(PULP_CBC_CMD(msg=0))
            
            if LpStatus[prob.status] == 'Optimal':
                self.xs = np.zeros([self.length, self.length])
                for (i, j), var in x_vars.items():
                    if value(var) == 1:
                        self.xs[i, j] = 1
                
                path_indices = list(zip(*np.nonzero(self.xs)))
                
                if path_indices:
                    self.path = [
                        (self.index2currency[i], self.index2currency[j])
                        for i, j in path_indices
                    ]
                    
                    self.path = self._sort_path(self.path)
                    
                    # ✅ FIX: Check if path is blocked
                    if self._is_path_blocked(self.path):
                        logger.debug(f"Path already found recently, skipping")
                        return []
                    
                    path_coins = [(p[0].split('_')[1], p[1].split('_')[1]) for p in self.path]
                    logger.info(f"🔍 LP found path: {' → '.join([p[0] for p in path_coins] + [path_coins[-1][1]])}")
                    
                    simulated_profit = self._simulate_path_profit()
                    
                    if simulated_profit is None:
                        logger.warning("❌ Simulation failed, skipping path")
                        return []
                    
                    logger.info(f"📊 Simulated profit: {simulated_profit:.4f}%")
                    self.profit_percent = simulated_profit
                    
                    if self.profit_percent >= self.min_profit:
                        opp = self._create_opportunity()
                        opportunities.append(opp)
                        
                        # ✅ FIX: Block this path temporarily
                        self._block_path(self.path)
                        
                        logger.info(f"✅ Found opportunity: {self.profit_percent:.2f}% profit, path length: {len(self.path)}")
                    else:
                        logger.debug(f"⏭️  Profit {self.profit_percent:.2f}% below threshold {self.min_profit}%")
            else:
                logger.debug(f"PuLP status: {LpStatus[prob.status]}")
            
        except Exception as e:
            logger.error(f"Error solving PuLP model: {e}", exc_info=True)
        
        return opportunities
    
    def _simulate_path_profit(self) -> Optional[float]:
        """Simulate actual profit through the path"""
        try:
            if not self.path:
                return None
            
            amount = 1.0
            
            logger.debug(f"=== Simulating path with {len(self.path)} steps ===")
            logger.debug(f"Starting amount: {amount}")
            
            for step_num, (from_cur, to_cur) in enumerate(self.path, 1):
                from_idx = self.currency2index[from_cur]
                to_idx = self.currency2index[to_cur]
                
                price = self.transit_price_matrix[from_idx, to_idx]
                fee = self.commission_matrix[from_idx, to_idx]
                
                from_coin = from_cur.split('_')[1]
                to_coin = to_cur.split('_')[1]
                
                logger.debug(f"\nStep {step_num}: {from_coin} → {to_coin}")
                logger.debug(f"  Before: {amount:.8f} {from_coin}")
                logger.debug(f"  Price: {price:.8f}")
                logger.debug(f"  Fee: {fee:.4%}")
                
                if price <= 0:
                    logger.warning(f"Invalid price: {price}")
                    return None
                
                amount = amount * price
                logger.debug(f"  After price: {amount:.8f}")
                
                amount = amount * (1 - fee)
                logger.debug(f"  After fee: {amount:.8f} {to_coin}")
            
            profit_percent = (amount - 1) * 100
            
            logger.debug(f"\n=== Final result ===")
            logger.debug(f"Final amount: {amount:.8f}")
            logger.debug(f"Profit: {profit_percent:.4f}%")
            
            return profit_percent
            
        except Exception as e:
            logger.error(f"Error simulating path: {e}", exc_info=True)
            return None
    
    def _sort_path(self, path: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """Sort path head-to-tail"""
        if not path:
            return []
        
        next_map = {p[0]: p for p in path}
        sorted_path = [path[0]]
        current = path[0]
        
        while len(sorted_path) < len(path):
            next_cur = current[1]
            if next_cur not in next_map:
                break
            
            next_pair = next_map[next_cur]
            if next_pair in sorted_path:
                break
            
            sorted_path.append(next_pair)
            current = next_pair
        
        return sorted_path
    
    def _create_opportunity(self) -> Dict:
        """Create opportunity dict"""
        detailed_path = []
        
        for from_cur, to_cur in self.path:
            from_idx = self.currency2index[from_cur]
            to_idx = self.currency2index[to_cur]
            
            price = self.transit_price_matrix[from_idx, to_idx]
            fee = self.commission_matrix[from_idx, to_idx]
            
            from_exc = from_cur.split('_')[0]
            to_exc = to_cur.split('_')[0]
            from_coin = from_cur.split('_')[1]
            to_coin = to_cur.split('_')[1]
            
            if from_exc == to_exc:
                pair = f"{from_coin}/{to_coin}"
                action = f"Sell {from_coin} → Buy {to_coin}"
                side = 'sell'
            else:
                pair = f"{from_coin} ({from_exc} → {to_exc})"
                action = f"Transfer {from_coin} from {from_exc} to {to_exc}"
                side = 'transfer'
            
            detailed_path.append({
                'pair': pair,
                'from': from_cur,
                'to': to_cur,
                'price': float(price),
                'fee': float(fee),
                'action': action,
                'amount': 0,
                'side': side
            })
        
        first_exchange = self.path[0][0].split('_')[0]
        avg_fee = np.mean([p['fee'] for p in detailed_path]) * 100 if detailed_path else 0
        
        return {
            'id': generate_opportunity_id(),
            'type': 'cross_exchange' if self.inter_exchange_trading and any(
                p[0].split('_')[0] != p[1].split('_')[0] for p in self.path
            ) else 'triangular',
            'exchange': first_exchange,
            'path': detailed_path,
            'raw_path': self.path,
            'profit_percent': float(self.profit_percent),
            'expected_profit_usd': float(self.trade_size_usd * self.profit_percent / 100),
            'trade_size': float(self.trade_size_usd),
            'fees': float(avg_fee),
            'slippage': 0.1,
            'net_profit': float(self.profit_percent),
            'exec_time': len(self.path) * 0.8,
            'liquidity_score': 75,
            'timestamp': get_utc_now()
        }
    
    def have_opportunity(self) -> bool:
        """Check if optimizer found opportunity"""
        return len(self.path) > 0 and self.profit_percent >= self.min_profit