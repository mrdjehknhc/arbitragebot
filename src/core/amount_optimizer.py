"""
Amount Optimizer using PuLP Linear Programming
Optimizes trading amounts for arbitrage paths
Based on crypto-arbitrage-framework but modernized and improved
"""
import numpy as np
from pulp import *
from typing import Dict, List, Optional, Tuple
from collections import OrderedDict
from ..utils.logger import get_logger
from ..utils.validators import Validators
from .orderbook_analyzer import OrderbookAnalyzer

logger = get_logger()


class AmountOptimizer:
    """
    Optimizes trading amounts for arbitrage path using Linear Programming
    
    Key improvements over original:
    - Uses only PuLP (no CPLEX dependency)
    - Async support
    - Better error handling
    - Type hints
    - Cleaner code structure
    """
    
    def __init__(
        self,
        orderbook_depth: int = 20,
        max_slippage_percent: float = 0.5,
        min_trade_usd: float = 10.0,
        default_precision: int = 8
    ):
        """
        Initialize optimizer
        
        Args:
            orderbook_depth: Number of orders to consider
            max_slippage_percent: Max acceptable slippage
            min_trade_usd: Minimum trade size in USD
            default_precision: Default decimal precision
        """
        self.orderbook_depth = orderbook_depth
        self.max_slippage = max_slippage_percent
        self.min_trade_usd = min_trade_usd
        self.default_precision = default_precision
        
        # Orderbook analyzer
        self.ob_analyzer = OrderbookAnalyzer(max_slippage_percent)
        
        # Solution storage
        self.solution: OrderedDict = OrderedDict()
        self.profit_amount: float = 0.0
        self.profit_percent: float = 0.0
        
        logger.debug(
            f"💎 AmountOptimizer init: "
            f"depth={orderbook_depth}, "
            f"max_slippage={max_slippage_percent}%"
        )
    
    async def optimize(
        self,
        path: List[Tuple[str, str]],
        orderbooks: Dict[str, Dict],
        balances: Dict[str, float],
        fees: Dict[Tuple[str, str], float],
        prices: Dict[str, float],
        initial_amount: float = 100.0
    ) -> Optional[Dict]:
        """
        Optimize trading amounts for arbitrage path
        
        Args:
            path: List of (from_currency, to_currency) tuples
            orderbooks: Dict {(from, to): orderbook}
            balances: Dict {currency: balance}
            fees: Dict {(from, to): fee_rate}
            prices: Dict {currency: usd_price}
            initial_amount: Starting amount in USD
        
        Returns:
            Optimized solution dict or None if no solution
        """
        try:
            # Validate path
            path = Validators.validate_path(path)
            
            logger.debug(f"🔍 Optimizing amounts for path length {len(path)}")
            
            # Build optimization model
            model = self._build_model(
                path, orderbooks, balances, fees, prices, initial_amount
            )
            
            if model is None:
                return None
            
            # Solve
            solution = self._solve_model(model, path, orderbooks, fees, prices)
            
            if solution:
                logger.info(
                    f"✅ Optimization complete: "
                    f"profit={solution['profit_percent']:.4f}%, "
                    f"profit_usd=${solution['profit_usd']:.2f}"
                )
            else:
                logger.debug("No feasible solution found")
            
            return solution
            
        except Exception as e:
            logger.error(f"Error in optimization: {e}", exc_info=True)
            return None
    
    def _build_model(
        self,
        path: List[Tuple[str, str]],
        orderbooks: Dict,
        balances: Dict,
        fees: Dict,
        prices: Dict,
        initial_amount: float
    ) -> Optional[LpProblem]:
        """Build PuLP optimization model"""
        try:
            path_length = len(path)
            
            # Create model
            model = LpProblem("AmountOptimization", LpMaximize)
            
            # Decision variables: amount to trade at each step
            amounts = []
            for i in range(path_length):
                var = LpVariable(f"amount_{i}", lowBound=0)
                amounts.append(var)
            
            # Build constraints and objective
            self._add_constraints(
                model, amounts, path, orderbooks, balances, fees, prices, initial_amount
            )
            
            self._set_objective(
                model, amounts, path, fees, prices
            )
            
            return model
            
        except Exception as e:
            logger.error(f"Error building model: {e}")
            return None
    
    def _add_constraints(
        self,
        model: LpProblem,
        amounts: List[LpVariable],
        path: List[Tuple],
        orderbooks: Dict,
        balances: Dict,
        fees: Dict,
        prices: Dict,
        initial_amount: float
    ):
        """Add constraints to model"""
        
        # 1. Flow constraints - each step depends on previous
        for i in range(len(path)):
            from_cur, to_cur = path[i]
            
            # Get orderbook
            ob_key = (from_cur, to_cur)
            if ob_key not in orderbooks:
                logger.warning(f"Missing orderbook for {ob_key}")
                continue
            
            orderbook = orderbooks[ob_key]
            fee = fees.get(ob_key, 0.001)
            
            # Determine trade direction
            if '/' in from_cur or '/' in to_cur:
                # This is intra-exchange trade
                # Analyze depth
                analysis = self.ob_analyzer.analyze_depth(
                    orderbook, 'sell', initial_amount
                )
                
                if analysis['feasible']:
                    # Liquidity constraint
                    max_amount = analysis['available_liquidity']
                    model += amounts[i] <= max_amount, f"liquidity_{i}"
            
            # Flow constraint: next step gets (current - fee) * price
            if i > 0:
                prev_amount = amounts[i-1]
                prev_fee = fees.get(path[i-1], 0.001)
                
                # Simplified: assume amount flows through
                # (Real implementation needs price conversions)
                model += amounts[i] <= prev_amount * (1 - prev_fee), f"flow_{i}"
        
        # 2. Balance constraints
        first_cur = path[0][0]
        if first_cur in balances:
            balance = balances[first_cur]
            balance_usd = balance * prices.get(first_cur.split('_')[-1], 1.0)
            
            if balance_usd >= self.min_trade_usd:
                model += amounts[0] <= balance_usd, "initial_balance"
        
        # 3. Minimum trade size
        for i, amount_var in enumerate(amounts):
            model += amount_var >= self.min_trade_usd, f"min_trade_{i}"
    
    def _set_objective(
        self,
        model: LpProblem,
        amounts: List[LpVariable],
        path: List[Tuple],
        fees: Dict,
        prices: Dict
    ):
        """Set optimization objective: maximize profit"""
        
        if not amounts:
            return
        
        # Objective: maximize final amount - initial amount
        # Simplified: profit = final_amount - initial_amount
        
        # Calculate final amount considering fees
        final_amount = amounts[0]
        
        for i in range(len(path)):
            fee = fees.get(path[i], 0.001)
            final_amount = final_amount * (1 - fee)
        
        # Objective: maximize profit
        profit = final_amount - amounts[0]
        model += profit
    
    def _solve_model(
        self,
        model: LpProblem,
        path: List[Tuple],
        orderbooks: Dict,
        fees: Dict,
        prices: Dict
    ) -> Optional[Dict]:
        """Solve optimization model and extract solution"""
        try:
            # Solve with PuLP
            model.solve(PULP_CBC_CMD(msg=0))
            
            status = LpStatus[model.status]
            
            if status != 'Optimal':
                logger.debug(f"Solver status: {status}")
                return None
            
            # Extract solution
            solution = self._extract_solution(model, path, orderbooks, fees, prices)
            
            return solution
            
        except Exception as e:
            logger.error(f"Error solving model: {e}")
            return None
    
    def _extract_solution(
        self,
        model: LpProblem,
        path: List[Tuple],
        orderbooks: Dict,
        fees: Dict,
        prices: Dict
    ) -> Dict:
        """Extract solution from solved model"""
        
        solution_steps = []
        total_cost = 0.0
        
        # Get variable values
        for i, (from_cur, to_cur) in enumerate(path):
            var_name = f"amount_{i}"
            amount = 0.0
            
            # Find variable in model
            for var in model.variables():
                if var.name == var_name:
                    amount = var.varValue
                    break
            
            # Get orderbook and fee
            ob_key = (from_cur, to_cur)
            orderbook = orderbooks.get(ob_key, {})
            fee = fees.get(ob_key, 0.001)
            
            # Analyze execution
            if orderbook:
                analysis = self.ob_analyzer.analyze_depth(
                    orderbook, 'sell', amount
                )
                price = analysis.get('effective_price', 0)
            else:
                price = 0.0
            
            solution_steps.append({
                'step': i + 1,
                'from': from_cur,
                'to': to_cur,
                'amount': float(amount),
                'price': float(price),
                'fee_rate': float(fee),
                'cost': float(amount * price) if price > 0 else 0.0
            })
            
            total_cost += solution_steps[-1]['cost']
        
        # Calculate profit
        if solution_steps:
            initial_cost = solution_steps[0]['cost']
            final_proceeds = solution_steps[-1]['cost']
            
            profit_usd = final_proceeds - initial_cost
            profit_percent = (profit_usd / initial_cost * 100) if initial_cost > 0 else 0.0
        else:
            profit_usd = 0.0
            profit_percent = 0.0
        
        return {
            'steps': solution_steps,
            'profit_usd': profit_usd,
            'profit_percent': profit_percent,
            'total_cost': total_cost,
            'feasible': profit_percent > 0
        }
    
    def optimize_simple(
        self,
        path: List[Tuple[str, str]],
        prices: Dict[Tuple[str, str], float],
        fees: Dict[Tuple[str, str], float],
        balance: float
    ) -> Dict:
        """
        Simplified optimization without orderbooks
        Uses fixed prices and fees
        
        Args:
            path: Trading path
            prices: Dict {(from, to): price}
            fees: Dict {(from, to): fee_rate}
            balance: Starting balance
        
        Returns:
            Solution dict
        """
        try:
            amount = balance
            steps = []
            
            for from_cur, to_cur in path:
                pair = (from_cur, to_cur)
                price = prices.get(pair, 0)
                fee = fees.get(pair, 0.001)
                
                if price <= 0:
                    return {'steps': [], 'profit_percent': -100, 'feasible': False}
                
                # Apply price conversion
                amount = amount * price
                
                # Apply fee
                amount = amount * (1 - fee)
                
                steps.append({
                    'from': from_cur,
                    'to': to_cur,
                    'amount': amount,
                    'price': price,
                    'fee_rate': fee
                })
            
            profit_percent = ((amount - balance) / balance) * 100
            
            return {
                'steps': steps,
                'profit_usd': amount - balance,
                'profit_percent': profit_percent,
                'total_cost': amount,
                'feasible': profit_percent > 0
            }
            
        except Exception as e:
            logger.error(f"Error in simple optimization: {e}")
            return {'steps': [], 'profit_percent': -100, 'feasible': False}
    
    def validate_solution(self, solution: Dict, min_profit_percent: float = 0.3) -> bool:
        """
        Validate optimization solution
        
        Args:
            solution: Solution dict
            min_profit_percent: Minimum acceptable profit
        
        Returns:
            True if solution is valid and profitable
        """
        if not solution or not solution.get('feasible'):
            return False
        
        if solution.get('profit_percent', 0) < min_profit_percent:
            return False
        
        steps = solution.get('steps', [])
        if not steps:
            return False
        
        # Check all amounts are positive
        for step in steps:
            if step.get('amount', 0) <= 0:
                return False
        
        return True