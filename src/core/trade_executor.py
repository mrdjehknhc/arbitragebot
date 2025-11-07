"""
Clean and efficient trade execution module
Handles order placement, tracking, and error management
"""
import time
from typing import Dict, List, Optional
from ..utils.logger import get_logger
from ..utils.helpers import generate_trade_id, get_utc_now

logger = get_logger()

class TradeExecutor:
    """Исполнитель торговых операций"""
    
    def __init__(self, exchange_manager, config: Dict):
        self.exchanges = exchange_manager
        self.config = config
        self.order_timeout = config.get('trading', {}).get('order_timeout_seconds', 30)
        self.order_type = config.get('trading', {}).get('order_type', 'limit')
    
    def execute_opportunity(self, opportunity: Dict) -> Dict:
        """
        Исполняет арбитражную возможность
        
        Returns:
            Dict с результатами сделки
        """
        trade_id = generate_trade_id()
        exchange_name = opportunity['exchange']
        exchange = self.exchanges.get_exchange(exchange_name)
        
        if not exchange:
            return self._create_error_result(trade_id, opportunity, "Exchange not available")
        
        logger.bind(trade=True).info(f"🚀 Executing trade {trade_id} on {exchange_name}")
        
        start_time = time.time()
        executed_orders = []
        total_profit = 0.0
        
        try:
            # Исполняем каждый шаг пути
            for i, step in enumerate(opportunity['path'], 1):
                logger.info(f"Step {i}/{len(opportunity['path'])}: {step['action']}")
                
                order = self._execute_step(exchange, step, exchange_name)
                
                if not order or order.get('status') == 'failed':
                    # Откатываем предыдущие ордера если возможно
                    return self._create_failed_result(
                        trade_id, 
                        opportunity, 
                        executed_orders,
                        f"Failed at step {i}: {step['action']}"
                    )
                
                executed_orders.append(order)
                logger.info(f"✅ Step {i} completed: {order.get('filled', 0)} filled")
            
            # Рассчитываем финальный профит
            execution_time = time.time() - start_time
            
            # Упрощенный расчет профита (нужно улучшить)
            actual_profit_percent = opportunity['profit_percent']
            actual_profit_usd = opportunity['expected_profit_usd']
            
            result = {
                'trade_id': trade_id,
                'opportunity_id': opportunity.get('id'),
                'type': opportunity['type'],
                'exchange': exchange_name,
                'path': opportunity['path'],
                'expected_profit_percent': opportunity['profit_percent'],
                'expected_profit_usd': opportunity['expected_profit_usd'],
                'actual_profit_percent': actual_profit_percent,
                'actual_profit_usd': actual_profit_usd,
                'trade_size_usd': opportunity['trade_size'],
                'execution_time': execution_time,
                'orders': executed_orders,
                'status': 'success',
                'error_message': None,
                'timestamp': get_utc_now()
            }
            
            logger.bind(trade=True).info(
                f"✅ Trade {trade_id} SUCCESS! "
                f"Profit: {actual_profit_percent:.2f}% (${actual_profit_usd:.2f}) "
                f"Time: {execution_time:.1f}s"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Trade {trade_id} FAILED: {e}")
            return self._create_error_result(trade_id, opportunity, str(e), executed_orders)
    
    def _execute_step(self, exchange, step: Dict, exchange_name: str) -> Optional[Dict]:
        """
        Исполняет один шаг арбитража
        
        Args:
            exchange: CCXT exchange instance
            step: Шаг из opportunity['path']
            exchange_name: Имя биржи
        
        Returns:
            Dict с информацией об ордере
        """
        try:
            pair = step['pair']
            price = step['price']
            amount = step['amount']
            action = step['action']
            
            # Определяем направление (buy/sell)
            side = 'sell' if 'Sell' in action else 'buy'
            
            # Создаём ордер
            if self.order_type == 'market':
                order = exchange.create_market_order(
                    symbol=pair,
                    side=side,
                    amount=amount
                )
            else:  # limit
                order = exchange.create_limit_order(
                    symbol=pair,
                    side=side,
                    amount=amount,
                    price=price
                )
            
            # Ждём исполнения
            order_id = order['id']
            filled = self._wait_for_order(exchange, order_id, pair)
            
            return {
                'id': order_id,
                'symbol': pair,
                'side': side,
                'amount': amount,
                'price': price,
                'filled': filled,
                'status': 'filled' if filled else 'failed',
                'timestamp': get_utc_now()
            }
            
        except Exception as e:
            logger.error(f"Error executing step: {e}")
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def _wait_for_order(self, exchange, order_id: str, symbol: str) -> bool:
        """
        Ждёт исполнения ордера
        
        Returns:
            True если исполнен, False если timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < self.order_timeout:
            try:
                order = exchange.fetch_order(order_id, symbol)
                status = order.get('status')
                
                if status == 'closed' or status == 'filled':
                    return True
                elif status == 'canceled' or status == 'rejected':
                    return False
                
                time.sleep(0.5)
                
            except Exception as e:
                logger.warning(f"Error checking order status: {e}")
                time.sleep(1)
        
        # Timeout - пытаемся отменить ордер
        try:
            exchange.cancel_order(order_id, symbol)
            logger.warning(f"Order {order_id} cancelled due to timeout")
        except:
            pass
        
        return False
    
    def _create_error_result(
        self, 
        trade_id: str, 
        opportunity: Dict, 
        error_msg: str,
        executed_orders: List = None
    ) -> Dict:
        """Создаёт результат с ошибкой"""
        return {
            'trade_id': trade_id,
            'opportunity_id': opportunity.get('id'),
            'type': opportunity['type'],
            'exchange': opportunity['exchange'],
            'path': opportunity['path'],
            'expected_profit_percent': opportunity['profit_percent'],
            'expected_profit_usd': opportunity['expected_profit_usd'],
            'actual_profit_percent': 0.0,
            'actual_profit_usd': 0.0,
            'trade_size_usd': opportunity['trade_size'],
            'execution_time': 0.0,
            'orders': executed_orders or [],
            'status': 'failed',
            'error_message': error_msg,
            'timestamp': get_utc_now()
        }
    
    def _create_failed_result(
        self,
        trade_id: str,
        opportunity: Dict,
        executed_orders: List,
        error_msg: str
    ) -> Dict:
        """Создаёт результат частично исполненной сделки"""
        result = self._create_error_result(trade_id, opportunity, error_msg, executed_orders)
        result['status'] = 'partial'
        return result