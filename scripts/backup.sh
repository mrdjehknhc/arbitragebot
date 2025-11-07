<<'BACKUP_SCRIPT'
#!/bin/bash
set -e

BACKUP_DIR="backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/backup_${TIMESTAMP}.tar.gz"

echo "💾 Starting backup..."

# Create backup directory
mkdir -p $BACKUP_DIR

# Create backup
echo "📦 Creating backup archive..."
tar -czf $BACKUP_FILE \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='logs/*.log' \
    data/ config/ .env 2>/dev/null || true

if [ -f "$BACKUP_FILE" ]; then
    SIZE=$(du -h $BACKUP_FILE | cut -f1)
    echo "✅ Backup created: $BACKUP_FILE ($SIZE)"
    
    # Keep only last 10 backups
    echo "🧹 Cleaning old backups..."
    ls -t $BACKUP_DIR/backup_*.tar.gz 2>/dev/null | tail -n +11 | xargs -r rm 2>/dev/null || true
    echo "✅ Cleanup complete"
else
    echo "❌ Backup failed"
    exit 1
fi

echo "✅ Backup complete!"
BACKUP_SCRIPT
