#!/usr/bin/env python3
"""
CEX Arbitrage Bot v3 - Enhanced with Async Support
Main Entry Point with Three-Stage Arbitrage Detection
"""
import sys
import argparse
import time
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.utils.config_loader import ConfigLoader
from src.utils.logger import get_logger
from src.services.database import DatabaseService
from src.services.telegram_notifier import TelegramNotifier
from src.services.reporter import Reporter
from src.exchanges import create_exchange_manager
from src.security.risk_manager import RiskManager

logger = get_logger()

class ArbitrageBot:
    """Main arbitrage bot with enhanced async support"""
    
    def __init__(self, test_mode: bool = False, use_async: bool = True):
        logger.info("🚀 Initializing Enhanced Arbitrage Bot v3...")
        
        # Load config
        self.config_loader = ConfigLoader()
        self.config = self.config_loader.load()
        
        if not self.config_loader.validate():
            raise ValueError("Invalid configuration")
        
        # Initialize services
        self.db = DatabaseService()
        self.telegram = TelegramNotifier(self.config['main'])
        self.reporter = Reporter(self.db, self.telegram)
        self.exchange_manager = create_exchange_manager(self.config['main'])
        self.risk_manager = RiskManager(self.config['main'])
        
        self.test_mode = test_mode
        self.use_async = use_async
        self.running = False
        
        logger.info("✅ Bot v3 initialized successfully")
        
        if use_async:
            logger.info("⚡ Async mode ENABLED (faster!)")
        else:
            logger.info("🐢 Sync mode (backward compatible)")
    
    def start(self):
        """Start bot (sync wrapper)"""
        if self.use_async:
            # Run async version
            try:
                asyncio.run(self.start_async())
            except KeyboardInterrupt:
                logger.info("⏸️  Bot stopped by user")
        else:
            # Run sync version (legacy)
            self.start_sync()
    
    async def start_async(self):
        """Start bot (async version)"""
        if self.running:
            logger.warning("Bot is already running")
            return
        
        logger.info("▶️  Starting bot (async mode)...")
        self.running = True
        
        if self.test_mode:
            logger.info("🧪 Running in TEST MODE (no real trades)")
        
        # Test exchange connections
        await self.test_connections_async()
        
        # Main loop
        try:
            await self._main_loop_async()
        except KeyboardInterrupt:
            logger.info("⏸️  Bot stopped by user")
        except Exception as e:
            logger.error(f"❌ Critical error: {e}", exc_info=True)
            self.db.log_error('critical', str(e), stack=str(e))
        finally:
            self.stop()
    
    def start_sync(self):
        """Start bot (sync version - legacy)"""
        if self.running:
            logger.warning("Bot is already running")
            return
        
        logger.info("▶️  Starting bot (sync mode)...")
        self.running = True
        
        if self.test_mode:
            logger.info("🧪 Running in TEST MODE (no real trades)")
        
        # Test connections
        self.test_connections()
        
        # Main loop
        try:
            self._main_loop_sync()
        except KeyboardInterrupt:
            logger.info("⏸️  Bot stopped by user")
        except Exception as e:
            logger.error(f"❌ Critical error: {e}", exc_info=True)
            self.db.log_error('critical', str(e), stack=str(e))
        finally:
            self.stop()
    
    async def _main_loop_async(self):
        """Main loop (async version)"""
        from src.core.arbitrage_engine import ArbitrageEngine
        from src.core.trade_executor import TradeExecutor
        
        scan_interval = self.config['main']['monitoring']['scan_interval_seconds']
        auto_execute = self.config['main']['trading']['auto_execute']
        
        # Initialize
        engine = ArbitrageEngine(self.exchange_manager, self.config['main'])
        executor = TradeExecutor(self.exchange_manager, self.config['main'])
        
        logger.info(f"🔍 Starting main loop (scan every {scan_interval}s)")
        logger.info(f"⚡ Auto-execute: {'ON' if auto_execute else 'OFF'}")
        logger.info(f"💎 Enhanced mode: THREE-STAGE (PathOpt → OrderbookCheck → AmountOpt)")
        
        scan_count = 0
        
        while self.running:
            try:
                scan_count += 1
                start_time = time.time()
                
                logger.info(f"━━━ Scan #{scan_count} ━━━")
                
                # ASYNC SCANNING (faster!)
                opportunities = await engine.scan_all_exchanges_async()
                
                if not opportunities:
                    logger.info("No opportunities found")
                    await asyncio.sleep(scan_interval)
                    continue
                
                logger.info(f"🔍 Found {len(opportunities)} opportunities")
                
                # Process top opportunities
                for opp in opportunities[:5]:
                    # Validate with risk manager
                    valid, reason = self.risk_manager.validate_opportunity(opp)
                    
                    if not valid:
                        logger.warning(f"⏭️  Skipped: {reason}")
                        
                        # Save skipped opportunity
                        if self.config['main']['monitoring']['save_opportunities']:
                            self.db.save_opportunity({
                                **opp,
                                'executed': False,
                                'skipped_reason': reason
                            })
                        
                        # Notify if profit is high
                        if opp['profit_percent'] > 1.0:
                            self.telegram.notify_skipped({
                                'id': opp['id'],
                                'profit_percent': opp['profit_percent'],
                                'profit_usd': opp.get('expected_profit_usd', 0),
                                'reason': reason,
                                'recommendation': 'Check risk limits'
                            })
                        continue
                    
                    # Notify opportunity found
                    self.telegram.notify_opportunity(opp)
                    
                    # Save opportunity
                    if self.config['main']['monitoring']['save_opportunities']:
                        self.db.save_opportunity({
                            **opp,
                            'executed': False
                        })
                    
                    # Execute if enabled
                    if auto_execute and not self.test_mode:
                        logger.info(f"⚡ Executing opportunity {opp['id']}")
                        
                        trade_result = executor.execute_opportunity(opp)
                        
                        # Record trade
                        self.risk_manager.record_trade(trade_result)
                        
                        # Save to DB
                        if self.config['main']['monitoring']['save_trades']:
                            self.db.save_trade(trade_result)
                        
                        # Notify result
                        if trade_result['status'] == 'success':
                            self.telegram.notify_trade(trade_result)
                        else:
                            self.telegram.notify_error({
                                'trade_id': trade_result['trade_id'],
                                'loss': 0,
                                'loss_percent': 0,
                                'message': trade_result.get('error_message', 'Unknown error'),
                                'details': str(trade_result.get('orders', []))
                            })
                        
                        # Pause between trades
                        await asyncio.sleep(2)
                    else:
                        if self.test_mode:
                            logger.info(
                                f"🧪 TEST MODE: Would execute {opp['id']} - "
                                f"Profit: {opp['profit_percent']:.2f}% "
                                f"(${opp['expected_profit_usd']:.2f})"
                            )
                        else:
                            logger.info(
                                f"⏸️  Auto-execute OFF: {opp['id']} - "
                                f"Profit: {opp['profit_percent']:.2f}%"
                            )
                
                # Log performance
                scan_time = time.time() - start_time
                logger.info(f"⏱️  Scan completed in {scan_time:.2f}s")
                
                # Sleep
                await asyncio.sleep(scan_interval)
                
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                self.db.log_error('main_loop', str(e))
                await asyncio.sleep(10)
    
    def _main_loop_sync(self):
        """Main loop (sync version - legacy)"""
        from src.core.arbitrage_engine import ArbitrageEngine
        from src.core.trade_executor import TradeExecutor
        
        scan_interval = self.config['main']['monitoring']['scan_interval_seconds']
        auto_execute = self.config['main']['trading']['auto_execute']
        
        engine = ArbitrageEngine(self.exchange_manager, self.config['main'])
        executor = TradeExecutor(self.exchange_manager, self.config['main'])
        
        logger.info(f"🔍 Starting main loop (scan every {scan_interval}s)")
        logger.info(f"⚡ Auto-execute: {'ON' if auto_execute else 'OFF'}")
        
        scan_count = 0
        
        while self.running:
            try:
                scan_count += 1
                start_time = time.time()
                
                logger.info(f"━━━ Scan #{scan_count} ━━━")
                
                # Sync scanning
                opportunities = engine.scan_all_exchanges()
                
                if not opportunities:
                    logger.info("No opportunities found")
                    time.sleep(scan_interval)
                    continue
                
                logger.info(f"🔍 Found {len(opportunities)} opportunities")
                
                # Process opportunities (same as async version)
                # ... (same code as in async version)
                
                scan_time = time.time() - start_time
                logger.info(f"⏱️  Scan completed in {scan_time:.2f}s")
                
                time.sleep(scan_interval)
                
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                self.db.log_error('main_loop', str(e))
                time.sleep(10)
    
    def stop(self):
        """Stop bot"""
        logger.info("⏹️  Stopping bot...")
        self.running = False
        logger.info("✅ Bot stopped")
    
    def test_connections(self):
        """Test connections (sync)"""
        logger.info("🔌 Testing exchange connections...")
        results = self.exchange_manager.test_connections()
        
        if all(results.values()):
            logger.info("✅ All exchanges connected")
        else:
            failed = [k for k, v in results.items() if not v]
            logger.warning(f"⚠️  Failed connections: {', '.join(failed)}")
        
        return results
    
    async def test_connections_async(self):
        """Test connections (async)"""
        logger.info("🔌 Testing exchange connections...")
        
        try:
            # Use async connector
            from src.services.exchange_connector import MultiExchangeConnector
            
            connector = MultiExchangeConnector(self.config['main'])
            await connector.initialize()
            
            results = await connector.test_all_connections()
            
            await connector.close_all()
            
            if all(results.values()):
                logger.info("✅ All exchanges connected")
            else:
                failed = [k for k, v in results.items() if not v]
                logger.warning(f"⚠️  Failed connections: {', '.join(failed)}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error testing connections: {e}")
            # Fallback to sync
            return self.test_connections()
    
    def get_balances(self):
        """Get balances"""
        logger.info("💰 Fetching balances...")
        balances = self.exchange_manager.get_balances()
        
        for exc_name, balance in balances.items():
            logger.info(f"{exc_name.upper()}: {balance}")
        
        return balances
    
    def get_status(self):
        """Get status"""
        risk_status = self.risk_manager.get_status()
        
        status = {
            'running': self.running,
            'test_mode': self.test_mode,
            'async_mode': self.use_async,
            'risk': risk_status
        }
        
        logger.info(f"📊 Bot Status: {status}")
        return status


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description='CEX Arbitrage Bot v3')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Start command
    start_parser = subparsers.add_parser('start', help='Start the bot')
    start_parser.add_argument('--test-mode', action='store_true', help='Run in test mode')
    start_parser.add_argument('--sync', action='store_true', help='Use sync mode (slower)')
    
    # Stop command
    subparsers.add_parser('stop', help='Stop the bot')
    
    # Status command
    subparsers.add_parser('status', help='Show bot status')
    
    # Balance command
    subparsers.add_parser('balance', help='Show balances')
    
    # Test connections
    subparsers.add_parser('test-connections', help='Test connections')
    
    # Validate config
    subparsers.add_parser('validate-config', help='Validate config')
    
    # Report commands
    report_parser = subparsers.add_parser('report', help='Generate reports')
    report_parser.add_argument('--type', choices=['daily', 'weekly', 'monthly'], required=True)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        use_async = not getattr(args, 'sync', False)
        bot = ArbitrageBot(
            test_mode=getattr(args, 'test_mode', False),
            use_async=use_async
        )
        
        if args.command == 'start':
            bot.start()
        
        elif args.command == 'status':
            bot.get_status()
        
        elif args.command == 'balance':
            bot.get_balances()
        
        elif args.command == 'test-connections':
            bot.test_connections()
        
        elif args.command == 'validate-config':
            bot.config_loader.validate()
        
        elif args.command == 'report':
            if args.type == 'daily':
                report = bot.reporter.generate_daily_report()
                print(report)
            elif args.type == 'weekly':
                filepath = bot.reporter.generate_weekly_csv()
                logger.info(f"Report saved to: {filepath}")
            elif args.type == 'monthly':
                filepath = bot.reporter.generate_monthly_csv()
                logger.info(f"Report saved to: {filepath}")
    
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()