"""
Clean and efficient database service with SQLAlchemy
"""
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

Base = declarative_base()

class Opportunity(Base):
    """Таблица найденных арбитражных возможностей"""
    __tablename__ = 'opportunities'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    opportunity_id = Column(String(50), unique=True)
    type = Column(String(20))
    exchange = Column(String(20))
    path = Column(Text)
    expected_profit_percent = Column(Float)
    expected_profit_usd = Column(Float)
    trade_size_usd = Column(Float)
    fees_percent = Column(Float)
    slippage_percent = Column(Float)
    net_profit_percent = Column(Float)
    execution_time_estimate = Column(Float)
    liquidity_score = Column(Integer)
    executed = Column(Boolean, default=False)
    skipped_reason = Column(String(200))

class Trade(Base):
    """Таблица исполненных сделок"""
    __tablename__ = 'trades'
    
    id = Column(Integer, primary_key=True)
    trade_id = Column(String(50), unique=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    opportunity_id = Column(Integer)
    type = Column(String(20))
    exchange = Column(String(20))
    path = Column(Text)
    expected_profit_percent = Column(Float)
    expected_profit_usd = Column(Float)
    actual_profit_percent = Column(Float)
    actual_profit_usd = Column(Float)
    trade_size_usd = Column(Float)
    execution_time = Column(Float)
    orders = Column(Text)
    status = Column(String(20))
    error_message = Column(Text)

class Balance(Base):
    """Таблица снимков балансов"""
    __tablename__ = 'balances'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    exchange = Column(String(20))
    currency = Column(String(10))
    amount = Column(Float)
    usd_value = Column(Float)

class Error(Base):
    """Таблица ошибок"""
    __tablename__ = 'errors'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    type = Column(String(50))
    exchange = Column(String(20))
    message = Column(Text)
    stack_trace = Column(Text)
    resolved = Column(Boolean, default=False)

class PerformanceMetric(Base):
    """Таблица метрик производительности"""
    __tablename__ = 'performance_metrics'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    scan_time_ms = Column(Float)
    opportunities_found = Column(Integer)
    trades_executed = Column(Integer)
    avg_execution_time = Column(Float)
    cpu_usage_percent = Column(Float)
    memory_usage_mb = Column(Float)

class DatabaseService:
    """Сервис для работы с базой данных"""
    
    def __init__(self, db_path: str = "data/arb_bot.db"):
        Path("data").mkdir(exist_ok=True)
        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    def save_opportunity(self, opp_data: Dict) -> int:
        session = self.Session()
        try:
            import json
            opp = Opportunity(
                opportunity_id=opp_data.get('id'),
                type=opp_data.get('type'),
                exchange=opp_data.get('exchange'),
                path=json.dumps(opp_data.get('path', [])),
                expected_profit_percent=opp_data.get('profit_percent'),
                expected_profit_usd=opp_data.get('expected_profit_usd'),
                trade_size_usd=opp_data.get('trade_size'),
                fees_percent=opp_data.get('fees'),
                slippage_percent=opp_data.get('slippage'),
                net_profit_percent=opp_data.get('net_profit'),
                execution_time_estimate=opp_data.get('exec_time'),
                liquidity_score=opp_data.get('liquidity_score'),
                executed=opp_data.get('executed', False),
                skipped_reason=opp_data.get('skipped_reason')
            )
            session.add(opp)
            session.commit()
            return opp.id
        finally:
            session.close()
    
    def save_trade(self, trade_data: Dict) -> int:
        session = self.Session()
        try:
            import json
            trade = Trade(
                trade_id=trade_data.get('trade_id'),
                opportunity_id=trade_data.get('opportunity_id'),
                type=trade_data.get('type'),
                exchange=trade_data.get('exchange'),
                path=json.dumps(trade_data.get('path', [])),
                expected_profit_percent=trade_data.get('expected_profit_percent'),
                expected_profit_usd=trade_data.get('expected_profit_usd'),
                actual_profit_percent=trade_data.get('actual_profit_percent'),
                actual_profit_usd=trade_data.get('actual_profit_usd'),
                trade_size_usd=trade_data.get('trade_size_usd'),
                execution_time=trade_data.get('execution_time'),
                orders=json.dumps(trade_data.get('orders', [])),
                status=trade_data.get('status'),
                error_message=trade_data.get('error_message')
            )
            session.add(trade)
            session.commit()
            return trade.id
        finally:
            session.close()
    
    def save_balance(self, exchange: str, currency: str, amount: float, usd_value: float):
        session = self.Session()
        try:
            balance = Balance(exchange=exchange, currency=currency, amount=amount, usd_value=usd_value)
            session.add(balance)
            session.commit()
        finally:
            session.close()
    
    def log_error(self, error_type: str, message: str, exchange: str = None, stack: str = None):
        session = self.Session()
        try:
            error = Error(type=error_type, exchange=exchange, message=message, stack_trace=stack)
            session.add(error)
            session.commit()
        finally:
            session.close()
    
    def save_performance(self, metrics: Dict):
        session = self.Session()
        try:
            perf = PerformanceMetric(
                scan_time_ms=metrics.get('scan_time_ms'),
                opportunities_found=metrics.get('opportunities_found'),
                trades_executed=metrics.get('trades_executed'),
                avg_execution_time=metrics.get('avg_execution_time'),
                cpu_usage_percent=metrics.get('cpu_usage'),
                memory_usage_mb=metrics.get('memory_usage')
            )
            session.add(perf)
            session.commit()
        finally:
            session.close()
    
    def get_recent_trades(self, limit: int = 10) -> List[Trade]:
        session = self.Session()
        try:
            return session.query(Trade).order_by(Trade.timestamp.desc()).limit(limit).all()
        finally:
            session.close()
    
    def get_recent_opportunities(self, limit: int = 20) -> List[Opportunity]:
        session = self.Session()
        try:
            return session.query(Opportunity).order_by(Opportunity.timestamp.desc()).limit(limit).all()
        finally:
            session.close()