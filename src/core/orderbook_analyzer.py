"""
Orderbook depth analyzer for accurate slippage calculation
Analyzes market depth to determine optimal trading amounts
"""
import numpy as np
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, ROUND_DOWN
from ..utils.logger import get_logger
from ..utils.validators import Validators, ValidationError

logger = get_logger()


class OrderbookAnalyzer:
    """
    Analyzes orderbook depth for slippage calculation
    Critical for determining real trading amounts and prices
    """
    
    def __init__(self, max_slippage_percent: float = 0.5):
        """
        Initialize analyzer
        
        Args:
            max_slippage_percent: Maximum acceptable slippage
        """
        self.max_slippage_percent = max_slippage_percent
        logger.debug(f"📊 OrderbookAnalyzer init: max_slippage={max_slippage_percent}%")
    
    def analyze_depth(
        self,
        orderbook: Dict,
        side: str,
        target_amount: float
    ) -> Dict[str, float]:
        """
        Analyze orderbook depth for given amount
        
        Args:
            orderbook: Orderbook dict with 'bids' and 'asks'
            side: 'buy' or 'sell'
            target_amount: Amount we want to trade
        
        Returns:
            Dict with analysis:
            {
                'effective_price': float,      # Average execution price
                'total_cost': float,           # Total cost/proceeds
                'available_liquidity': float,  # Max tradeable amount
                'slippage_percent': float,     # Slippage vs top price
                'orders_needed': int,          # Number of orders consumed
                'feasible': bool              # Can execute without excess slippage
            }
        """
        try:
            # Validate inputs
            orderbook = Validators.validate_orderbook(orderbook)
            target_amount = Validators.validate_amount(target_amount)
            
            if side not in ['buy', 'sell']:
                raise ValidationError(f"Invalid side: {side}")
            
            # Get relevant orders (bids for sell, asks for buy)
            orders = orderbook['asks'] if side == 'buy' else orderbook['bids']
            
            if not orders:
                return self._empty_result()
            
            # Calculate execution
            result = self._calculate_execution(orders, target_amount, side)
            
            # Check if feasible
            result['feasible'] = (
                result['slippage_percent'] <= self.max_slippage_percent and
                result['available_liquidity'] >= target_amount
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing orderbook: {e}")
            return self._empty_result()
    
    def _calculate_execution(
        self,
        orders: List[List[float]],
        target_amount: float,
        side: str
    ) -> Dict[str, float]:
        """
        Calculate execution details across multiple orders
        
        Args:
            orders: List of [price, amount] pairs
            target_amount: Target trading amount
            side: 'buy' or 'sell'
        
        Returns:
            Execution analysis dict
        """
        top_price = float(orders[0][0])
        
        cumulative_amount = 0.0
        cumulative_cost = 0.0
        orders_needed = 0
        
        # Walk through orderbook
        for price, amount in orders:
            price = float(price)
            amount = float(amount)
            
            if cumulative_amount >= target_amount:
                break
            
            # How much we can take from this order
            remaining = target_amount - cumulative_amount
            take_amount = min(remaining, amount)
            
            # Add to cumulative
            cumulative_amount += take_amount
            cumulative_cost += take_amount * price
            orders_needed += 1
        
        # Calculate metrics
        if cumulative_amount > 0:
            effective_price = cumulative_cost / cumulative_amount
            slippage_percent = abs((effective_price - top_price) / top_price) * 100
        else:
            effective_price = top_price
            slippage_percent = 0.0
        
        # Calculate max available liquidity
        total_liquidity = sum(float(order[1]) for order in orders)
        
        return {
            'effective_price': effective_price,
            'total_cost': cumulative_cost,
            'available_liquidity': total_liquidity,
            'slippage_percent': slippage_percent,
            'orders_needed': orders_needed,
            'top_price': top_price,
            'executed_amount': cumulative_amount
        }
    
    def _empty_result(self) -> Dict[str, float]:
        """Return empty result when analysis fails"""
        return {
            'effective_price': 0.0,
            'total_cost': 0.0,
            'available_liquidity': 0.0,
            'slippage_percent': 100.0,
            'orders_needed': 0,
            'feasible': False
        }
    
    def get_max_amount_for_slippage(
        self,
        orderbook: Dict,
        side: str,
        max_slippage: Optional[float] = None
    ) -> float:
        """
        Calculate max tradeable amount within slippage limit
        
        Args:
            orderbook: Orderbook dict
            side: 'buy' or 'sell'
            max_slippage: Max slippage (uses self.max_slippage_percent if None)
        
        Returns:
            Max amount that can be traded within slippage limit
        """
        try:
            max_slippage = max_slippage or self.max_slippage_percent
            orderbook = Validators.validate_orderbook(orderbook)
            
            orders = orderbook['asks'] if side == 'buy' else orderbook['bids']
            if not orders:
                return 0.0
            
            top_price = float(orders[0][0])
            max_price = top_price * (1 + max_slippage / 100)
            
            # Find max amount within price range
            total_amount = 0.0
            
            for price, amount in orders:
                price = float(price)
                amount = float(amount)
                
                if side == 'buy' and price > max_price:
                    break
                if side == 'sell' and price < max_price:
                    break
                
                total_amount += amount
            
            return total_amount
            
        except Exception as e:
            logger.error(f"Error calculating max amount: {e}")
            return 0.0
    
    def calculate_price_impact(
        self,
        orderbook: Dict,
        side: str,
        amount: float
    ) -> Dict[str, float]:
        """
        Calculate price impact of a trade
        
        Args:
            orderbook: Orderbook dict
            side: 'buy' or 'sell'
            amount: Trade amount
        
        Returns:
            Dict with impact metrics:
            {
                'price_impact_percent': float,  # % price movement
                'before_price': float,          # Price before trade
                'after_price': float,           # Price after trade
                'depth_consumed': float         # % of depth consumed
            }
        """
        try:
            analysis = self.analyze_depth(orderbook, side, amount)
            
            if not analysis['feasible']:
                return {
                    'price_impact_percent': 100.0,
                    'before_price': 0.0,
                    'after_price': 0.0,
                    'depth_consumed': 100.0
                }
            
            before_price = analysis['top_price']
            after_price = analysis['effective_price']
            
            price_impact = abs((after_price - before_price) / before_price) * 100
            depth_consumed = (amount / analysis['available_liquidity']) * 100
            
            return {
                'price_impact_percent': price_impact,
                'before_price': before_price,
                'after_price': after_price,
                'depth_consumed': depth_consumed
            }
            
        except Exception as e:
            logger.error(f"Error calculating price impact: {e}")
            return {
                'price_impact_percent': 100.0,
                'before_price': 0.0,
                'after_price': 0.0,
                'depth_consumed': 100.0
            }
    
    def get_optimal_amount(
        self,
        orderbook: Dict,
        side: str,
        balance: float,
        min_amount: float = 10.0
    ) -> float:
        """
        Calculate optimal trading amount considering:
        - Available balance
        - Orderbook depth
        - Slippage limits
        
        Args:
            orderbook: Orderbook dict
            side: 'buy' or 'sell'
            balance: Available balance
            min_amount: Minimum viable amount
        
        Returns:
            Optimal amount to trade
        """
        try:
            # Get max amount within slippage
            max_amount = self.get_max_amount_for_slippage(orderbook, side)
            
            # Constrain by balance
            if side == 'buy':
                # For buys, balance is in quote currency
                # Need to convert to base amount
                top_price = float(orderbook['asks'][0][0])
                max_from_balance = balance / top_price
            else:
                # For sells, balance is in base currency
                max_from_balance = balance
            
            # Take minimum of constraints
            optimal = min(max_amount, max_from_balance)
            
            # Check minimum
            if optimal < min_amount:
                logger.debug(f"Optimal amount {optimal} below minimum {min_amount}")
                return 0.0
            
            return optimal
            
        except Exception as e:
            logger.error(f"Error calculating optimal amount: {e}")
            return 0.0
    
    def validate_execution_feasibility(
        self,
        orderbook: Dict,
        side: str,
        amount: float,
        balance: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate if trade execution is feasible
        
        Args:
            orderbook: Orderbook dict
            side: 'buy' or 'sell'
            amount: Trade amount
            balance: Available balance
        
        Returns:
            (is_feasible, reason_if_not)
        """
        try:
            # Analyze depth
            analysis = self.analyze_depth(orderbook, side, amount)
            
            # Check liquidity
            if analysis['available_liquidity'] < amount:
                return False, f"Insufficient liquidity: {analysis['available_liquidity']:.4f} < {amount:.4f}"
            
            # Check slippage
            if analysis['slippage_percent'] > self.max_slippage_percent:
                return False, f"Slippage too high: {analysis['slippage_percent']:.2f}% > {self.max_slippage_percent}%"
            
            # Check balance
            if side == 'buy':
                required_balance = analysis['total_cost']
            else:
                required_balance = amount
            
            if balance < required_balance:
                return False, f"Insufficient balance: {balance:.4f} < {required_balance:.4f}"
            
            return True, None
            
        except Exception as e:
            return False, f"Validation error: {e}"
    
    def get_layered_execution_plan(
        self,
        orderbook: Dict,
        side: str,
        total_amount: float,
        num_layers: int = 3
    ) -> List[Dict]:
        """
        Create layered execution plan to minimize slippage
        Splits large order into multiple smaller orders
        
        Args:
            orderbook: Orderbook dict
            side: 'buy' or 'sell'
            total_amount: Total amount to trade
            num_layers: Number of layers to split into
        
        Returns:
            List of execution layers:
            [
                {
                    'amount': float,
                    'price': float,
                    'slippage': float
                },
                ...
            ]
        """
        try:
            orders = orderbook['asks'] if side == 'buy' else orderbook['bids']
            if not orders:
                return []
            
            amount_per_layer = total_amount / num_layers
            layers = []
            
            for i in range(num_layers):
                analysis = self.analyze_depth(orderbook, side, amount_per_layer)
                
                if analysis['feasible']:
                    layers.append({
                        'layer': i + 1,
                        'amount': amount_per_layer,
                        'price': analysis['effective_price'],
                        'slippage': analysis['slippage_percent'],
                        'cost': analysis['total_cost']
                    })
            
            return layers
            
        except Exception as e:
            logger.error(f"Error creating execution plan: {e}")
            return []
    
    def calculate_spread(self, orderbook: Dict) -> Dict[str, float]:
        """
        Calculate bid-ask spread
        
        Args:
            orderbook: Orderbook dict
        
        Returns:
            Dict with spread metrics
        """
        try:
            orderbook = Validators.validate_orderbook(orderbook)
            
            best_bid = float(orderbook['bids'][0][0])
            best_ask = float(orderbook['asks'][0][0])
            
            spread_abs = best_ask - best_bid
            spread_percent = (spread_abs / best_bid) * 100
            mid_price = (best_bid + best_ask) / 2
            
            return {
                'best_bid': best_bid,
                'best_ask': best_ask,
                'spread_abs': spread_abs,
                'spread_percent': spread_percent,
                'mid_price': mid_price
            }
            
        except Exception as e:
            logger.error(f"Error calculating spread: {e}")
            return {
                'best_bid': 0.0,
                'best_ask': 0.0,
                'spread_abs': 0.0,
                'spread_percent': 100.0,
                'mid_price': 0.0
            }
    
    def estimate_round_trip_cost(
        self,
        orderbook: Dict,
        amount: float,
        fee_rate: float = 0.001
    ) -> Dict[str, float]:
        """
        Estimate total cost of round-trip trade (buy then sell)
        Useful for estimating arbitrage costs
        
        Args:
            orderbook: Orderbook dict
            amount: Amount to trade
            fee_rate: Trading fee rate
        
        Returns:
            Dict with cost breakdown
        """
        try:
            # Analyze buy
            buy_analysis = self.analyze_depth(orderbook, 'buy', amount)
            
            # Analyze sell
            sell_analysis = self.analyze_depth(orderbook, 'sell', amount)
            
            if not (buy_analysis['feasible'] and sell_analysis['feasible']):
                return {
                    'total_cost_percent': 100.0,
                    'spread_cost': 0.0,
                    'slippage_cost': 0.0,
                    'fee_cost': 0.0,
                    'feasible': False
                }
            
            # Calculate costs
            spread_cost = self.calculate_spread(orderbook)['spread_percent']
            
            buy_slippage = buy_analysis['slippage_percent']
            sell_slippage = sell_analysis['slippage_percent']
            slippage_cost = buy_slippage + sell_slippage
            
            fee_cost = fee_rate * 2 * 100  # Both buy and sell
            
            total_cost = spread_cost + slippage_cost + fee_cost
            
            return {
                'total_cost_percent': total_cost,
                'spread_cost': spread_cost,
                'slippage_cost': slippage_cost,
                'fee_cost': fee_cost,
                'feasible': True
            }
            
        except Exception as e:
            logger.error(f"Error estimating round-trip cost: {e}")
            return {
                'total_cost_percent': 100.0,
                'spread_cost': 0.0,
                'slippage_cost': 0.0,
                'fee_cost': 0.0,
                'feasible': False
            }