"""
Clean and robust risk management system
"""
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

@dataclass
class RiskLimits:
    """Лимиты рисков"""
    max_trade_size_usd: float = 1000
    max_daily_trades: int = 100
    max_daily_loss_usd: float = 100
    min_balance_usd: float = 100
    max_consecutive_losses: int = 5
    max_slippage_percent: float = 0.5
    emergency_stop_loss_percent: float = 5
    max_execution_time: float = 5.0
    min_liquidity_usd: float = 10000

class RiskManager:
    """Менеджер рисков для контроля торговли"""
    
    def __init__(self, config: Dict):
        self.limits = RiskLimits(**config.get('risk', {}))
        self.daily_stats = {
            'trades': 0,
            'losses': 0,
            'consecutive_losses': 0,
            'total_loss': 0.0,
            'last_reset': datetime.utcnow().date()
        }
        self.emergency_stop = False
        self.trade_history: List[Dict] = []
    
    def check_trade_allowed(self, trade_size: float, balance: float) -> tuple[bool, Optional[str]]:
        """Проверяет можно ли совершить сделку"""
        self._reset_daily_stats()
        
        if self.emergency_stop:
            return False, "Emergency stop activated"
        
        if trade_size > self.limits.max_trade_size_usd:
            return False, f"Trade size {trade_size:.2f} exceeds limit {self.limits.max_trade_size_usd}"
        
        if balance < self.limits.min_balance_usd:
            return False, f"Balance {balance:.2f} below minimum {self.limits.min_balance_usd}"
        
        if self.daily_stats['trades'] >= self.limits.max_daily_trades:
            return False, f"Daily trade limit reached: {self.limits.max_daily_trades}"
        
        if abs(self.daily_stats['total_loss']) >= self.limits.max_daily_loss_usd:
            return False, f"Daily loss limit reached: {self.limits.max_daily_loss_usd:.2f}"
        
        if self.daily_stats['consecutive_losses'] >= self.limits.max_consecutive_losses:
            return False, f"Consecutive losses limit reached: {self.limits.max_consecutive_losses}"
        
        return True, None
    
    def validate_opportunity(self, opp: Dict) -> tuple[bool, Optional[str]]:
        """Валидирует арбитражную возможность"""
        
        # Slippage check
        slippage = opp.get('slippage', 0)
        if slippage > self.limits.max_slippage_percent:
            return False, f"Slippage {slippage:.2f}% exceeds limit"
        
        # Execution time check
        exec_time = opp.get('exec_time', 0)
        if exec_time > self.limits.max_execution_time:
            return False, f"Execution time {exec_time:.1f}s exceeds limit"
        
        # Liquidity check - ИСПРАВЛЕНО!
        liquidity_score = opp.get('liquidity_score', 100)  # По умолчанию высокая
        if liquidity_score < 50:  # Минимальный score
            return False, f"Liquidity score {liquidity_score} too low"
        
        # Minimum profit
        net_profit = opp.get('net_profit', 0)
        if net_profit <= 0:
            return False, "Net profit is not positive"
        
        return True, None
    
    def record_trade(self, trade: Dict):
        """Записывает результат сделки"""
        self._reset_daily_stats()
        
        self.daily_stats['trades'] += 1
        profit = trade.get('actual_profit_usd', 0)
        
        if profit < 0:
            self.daily_stats['losses'] += 1
            self.daily_stats['consecutive_losses'] += 1
            self.daily_stats['total_loss'] += profit
        else:
            self.daily_stats['consecutive_losses'] = 0
        
        self.trade_history.append({
            'timestamp': datetime.utcnow(),
            'profit': profit,
            'status': trade.get('status')
        })
        
        self._check_emergency_stop()
    
    def _reset_daily_stats(self):
        """Сбрасывает дневную статистику в полночь"""
        today = datetime.utcnow().date()
        if today > self.daily_stats['last_reset']:
            self.daily_stats = {
                'trades': 0,
                'losses': 0,
                'consecutive_losses': 0,
                'total_loss': 0.0,
                'last_reset': today
            }
            cutoff = datetime.utcnow() - timedelta(hours=24)
            self.trade_history = [t for t in self.trade_history if t['timestamp'] > cutoff]
    
    def _check_emergency_stop(self):
        """Проверяет условия для аварийной остановки"""
        loss_percent = abs(self.daily_stats['total_loss']) / self.limits.max_daily_loss_usd * 100
        if loss_percent >= self.limits.emergency_stop_loss_percent * 100:
            self.emergency_stop = True
        
        if len(self.trade_history) >= 20:
            recent_trades = self.trade_history[-20:]
            wins = sum(1 for t in recent_trades if t['profit'] > 0)
            win_rate = wins / len(recent_trades)
            if win_rate < 0.4:
                self.emergency_stop = True
    
    def get_status(self) -> Dict:
        """Возвращает текущий статус рисков"""
        return {
            'emergency_stop': self.emergency_stop,
            'daily_trades': self.daily_stats['trades'],
            'daily_losses': self.daily_stats['losses'],
            'consecutive_losses': self.daily_stats['consecutive_losses'],
            'total_loss': self.daily_stats['total_loss'],
            'trades_remaining': self.limits.max_daily_trades - self.daily_stats['trades']
        }
    
    def reset_emergency_stop(self):
        """Сбрасывает аварийную остановку"""
        self.emergency_stop = False