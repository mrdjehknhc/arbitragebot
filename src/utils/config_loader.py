"""
Clean and efficient configuration loader
"""
import yaml
import os
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

class ConfigLoader:
    """Загрузчик конфигурации из YAML и ENV файлов"""
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.config: Dict[str, Any] = {}
        load_dotenv()
        
    def load(self) -> Dict[str, Any]:
        """Загружает все конфиги"""
        main_config = self._load_yaml('config.yml')
        
        # Tokens конфиг опционален
        try:
            tokens_config = self._load_yaml('tokens.yml')
        except FileNotFoundError:
            tokens_config = {'base_tokens': ['BTC', 'ETH', 'USDT']}
        
        self.config = {
            'main': main_config,
            'tokens': tokens_config
        }
        self._inject_env_vars()
        return self.config
    
    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """Загружает YAML файл"""
        path = self.config_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    
    def _inject_env_vars(self):
        """Подставляет переменные окружения в конфиг"""
        exchanges = self.config['main'].get('exchanges', {})
        
        for exc_name, exc_config in exchanges.items():
            if 'api_key_env' in exc_config:
                exc_config['api_key'] = os.getenv(exc_config['api_key_env'], '')
            if 'api_secret_env' in exc_config:
                exc_config['api_secret'] = os.getenv(exc_config['api_secret_env'], '')
            if 'passphrase_env' in exc_config:
                exc_config['passphrase'] = os.getenv(exc_config['passphrase_env'], '')
        
        # Telegram
        telegram = self.config['main'].get('telegram', {})
        if 'bot_token_env' in telegram:
            telegram['bot_token'] = os.getenv(telegram['bot_token_env'], '')
        if 'chat_id_env' in telegram:
            telegram['chat_id'] = os.getenv(telegram['chat_id_env'], '')
    
    def get(self, key: str, default: Any = None) -> Any:
        """Получает значение из конфига"""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        
        return value
    
    def validate(self) -> bool:
        """Валидирует конфигурацию"""
        required_keys = [
            'main.exchanges',
            'main.strategy',
            'main.trading',
            'main.risk'
        ]
        
        for key in required_keys:
            if self.get(key) is None:
                print(f"❌ Missing required config: {key}")
                return False
        
        print("✅ Configuration is valid")
        return True