"""
Fixed Telegram notifier with proper async handling
"""
import requests
from typing import Dict, List, Optional
from datetime import datetime
import pytz
from ..utils.logger import get_logger

logger = get_logger()

class TelegramNotifier:
    """Telegram уведомления БЕЗ asyncio проблем"""
    
    def __init__(self, config: Dict):
        self.config = config.get('telegram', {})
        self.enabled = self.config.get('enabled', False)
        
        if not self.enabled:
            logger.info("Telegram notifications disabled")
            return
        
        token = self.config.get('bot_token')
        chat_id = self.config.get('chat_id')
        
        if not token or not chat_id:
            logger.error("Telegram token or chat_id missing")
            self.enabled = False
            return
        
        self.token = token
        self.chat_id = chat_id
        self.notifications = self.config.get('notifications', {})
        self.min_profit = self.config.get('min_profit_to_notify_percent', 0.3)
        self.api_url = f"https://api.telegram.org/bot{self.token}"
    
    def send(self, message: str):
        """Синхронная отправка через requests"""
        if not self.enabled:
            return
        
        try:
            response = requests.post(
                f"{self.api_url}/sendMessage",
                json={
                    'chat_id': self.chat_id,
                    'text': message,
                    'parse_mode': 'HTML',
                    'disable_web_page_preview': True
                },
                timeout=10
            )
            
            if response.status_code == 200:
                logger.bind(telegram=True).info(f"Message sent successfully")
            else:
                logger.error(f"Telegram API error: {response.text}")
                
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
    
    def notify_opportunity(self, opp: Dict):
        """✅ FIX: Правильная проверка profit"""
        if not self.notifications.get('opportunities', True):
            return
        
        profit = opp.get('profit_percent', 0)
        
        # ✅ ИСПОЛЬЗУЕМ СВОЙ min_profit из telegram config!
        if profit < self.min_profit:
            logger.debug(f"Profit {profit:.2f}% < min_notify {self.min_profit}%")
            return
        
        msg = self._format_opportunity(opp)
        self.send(msg)
        logger.info(f"📱 Telegram: Opportunity sent ({profit:.2f}%)")
    
    def notify_trade(self, trade: Dict):
        """Уведомление о сделке"""
        if not self.notifications.get('trades', True):
            return
        
        msg = self._format_trade(trade)
        self.send(msg)
    
    def notify_error(self, error: Dict):
        """Уведомление об ошибке"""
        if not self.notifications.get('errors', True):
            return
        
        msg = self._format_error(error)
        self.send(msg)
    
    def notify_skipped(self, opp: Dict):
        """Уведомление о пропущенной возможности"""
        msg = self._format_skipped(opp)
        self.send(msg)
    
    def _format_opportunity(self, opp: Dict) -> str:
        """Форматирует сообщение о возможности"""
        path_str = ""
        for i, step in enumerate(opp.get('path', []), 1):
            path_str += f"{i}️⃣ {step.get('side', 'N/A').upper()} {step.get('pair', 'N/A')}\n"
            path_str += f"   Цена: {step.get('price', 0):.8f}\n"
            path_str += f"   Amount: {step.get('amount', 0):.4f}\n\n"
        
        msg = f"""🔍 <b>НАЙДЕНА ВОЗМОЖНОСТЬ!</b>

📊 <b>Тип:</b> {opp.get('type', 'N/A')}
🏦 <b>Биржа:</b> {opp.get('exchange', 'N/A')}
💰 <b>Расчетный профит:</b> {opp.get('profit_percent', 0):.2f}%
💵 <b>Прибыль (USD):</b> ~${opp.get('expected_profit_usd', 0):.2f}

📈 <b>Путь арбитража:</b>
{path_str}
💼 <b>Параметры:</b>
├─ Размер сделки: ${opp.get('trade_size', 0):.0f}
├─ Комиссии: -{opp.get('fees', 0):.2f}%
├─ Slippage учтен: -{opp.get('slippage', 0):.2f}%
├─ Чистый профит: {opp.get('net_profit', 0):.2f}%
└─ Время исполнения: ~{opp.get('exec_time', 0):.1f}s

⏰ <b>Найдено:</b> {self._format_time()}
🆔 <b>ID:</b> {opp.get('id', 'N/A')}

✅ <b>РЕКОМЕНДАЦИЯ:</b> Проверить и исполнить"""
        
        return msg
    
    def _format_trade(self, trade: Dict) -> str:
        """Форматирует сделку"""
        status_emoji = "✅" if trade['status'] == 'success' else "❌"
        
        msg = f"""{status_emoji} <b>СДЕЛКА ИСПОЛНЕНА!</b>

🆔 <b>Trade ID:</b> {trade.get('trade_id', 'N/A')}
📊 <b>Тип:</b> {trade.get('type', 'N/A')} ({trade.get('exchange', 'N/A')})
⏱️ <b>Время:</b> {trade.get('execution_time', 0):.1f}s

💰 <b>РЕЗУЛЬТАТ:</b>
├─ Ожидалось: {trade.get('expected_profit_percent', 0):.2f}%
├─ Получено: {trade.get('actual_profit_percent', 0):.2f}%
└─ Профит: ${trade.get('actual_profit_usd', 0):.2f}"""
        
        return msg
    
    def _format_error(self, error: Dict) -> str:
        """Форматирует ошибку"""
        return f"""🚨 <b>ОШИБКА!</b>

{error.get('message', 'Unknown error')}"""
    
    def _format_skipped(self, opp: Dict) -> str:
        """Форматирует пропущенную возможность"""
        return f"""⏭️ <b>ПРОПУЩЕНА</b>

Профит: {opp.get('profit_percent', 0):.2f}%
Причина: {opp.get('reason', 'Unknown')}"""
    
    def _format_time(self) -> str:
        """Форматирует время"""
        return datetime.now(pytz.UTC).strftime("%d.%m.%Y %H:%M:%S UTC")