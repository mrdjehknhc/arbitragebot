#!/bin/bash
# Monitoring script for Arbitrage Bot

set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 ARBITRAGE BOT MONITOR"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check if bot is running
if docker ps | grep -q "arb-bot-secure"; then
    echo "✅ Bot Status: RUNNING"
else
    echo "❌ Bot Status: STOPPED"
    exit 1
fi

# CPU and Memory usage
CONTAINER_ID=$(docker ps -qf "name=arb-bot-secure")
if [ ! -z "$CONTAINER_ID" ]; then
    STATS=$(docker stats --no-stream --format "table {{.CPUPerc}}\t{{.MemPerc}}" $CONTAINER_ID | tail -n 1)
    CPU=$(echo $STATS | awk '{print $1}')
    MEM=$(echo $STATS | awk '{print $2}')
    echo "💻 CPU: ${CPU} | Memory: ${MEM}"
fi

# Check database
if [ -f "data/arb_bot.db" ]; then
    DB_SIZE=$(du -h data/arb_bot.db | cut -f1)
    echo "💾 Database: ${DB_SIZE}"
    
    # Get today's stats
    TRADES_TODAY=$(sqlite3 data/arb_bot.db "SELECT COUNT(*) FROM trades WHERE DATE(timestamp) = DATE('now')" 2>/dev/null || echo "0")
    PROFIT_TODAY=$(sqlite3 data/arb_bot.db "SELECT ROUND(COALESCE(SUM(actual_profit_usd), 0), 2) FROM trades WHERE DATE(timestamp) = DATE('now') AND status='success'" 2>/dev/null || echo "0")
    
    echo "📈 Trades Today: ${TRADES_TODAY}"
    echo "💰 Profit Today: \$${PROFIT_TODAY}"
else
    echo "⚠️  Database not found"
fi

# Check errors
ERRORS=$(sqlite3 data/arb_bot.db "SELECT COUNT(*) FROM errors WHERE resolved=0" 2>/dev/null || echo "0")
if [ "$ERRORS" -gt 0 ]; then
    echo "⚠️  Unresolved Errors: ${ERRORS}"
fi

# Check disk space
DISK_USAGE=$(df -h . | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 80 ]; then
    echo "⚠️  Disk Usage: ${DISK_USAGE}% (HIGH!)"
else
    echo "💿 Disk Usage: ${DISK_USAGE}%"
fi

# Check logs size
if [ -d "logs" ]; then
    LOGS_SIZE=$(du -sh logs | cut -f1)
    echo "📝 Logs Size: ${LOGS_SIZE}"
fi

# Check last activity
if [ -f "logs/bot.log" ]; then
    LAST_LOG=$(tail -n 1 logs/bot.log | cut -d'|' -f1)
    echo "⏰ Last Activity: ${LAST_LOG}"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Monitoring complete"