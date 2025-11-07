set -e

echo "🚀 Setting up Arbitrage Bot..."
echo ""

# Check Python version
echo "📌 Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.10"

if (( $(echo "$PYTHON_VERSION < $REQUIRED_VERSION" | bc -l 2>/dev/null || echo "0") )); then
    echo "❌ Python $REQUIRED_VERSION or higher required. Found: $PYTHON_VERSION"
    exit 1
fi
echo "✅ Python $PYTHON_VERSION"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
fi

# Activate venv
echo ""
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "📥 Installing dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "✅ Dependencies installed"

# Create directories
echo ""
echo "📁 Creating directories..."
mkdir -p data logs data/reports config backups
touch data/.gitkeep logs/.gitkeep data/reports/.gitkeep
echo "✅ Directories created"

# Create .env if not exists
if [ ! -f ".env" ]; then
    echo ""
    echo "📝 Creating .env file..."
    cp .env.example .env
    echo "✅ .env created - PLEASE EDIT IT WITH YOUR API KEYS!"
    echo ""
    echo "⚠️  Edit .env now: nano .env"
else
    echo ""
    echo "✅ .env already exists"
fi

# Create default token config if not exist
if [ ! -f "config/tokens.yml" ]; then
    echo ""
    echo "📝 Creating default tokens.yml..."
    cat > config/tokens.yml << 'EOF'
base_tokens:
  - BTC
  - ETH
  - USDT
  - USDC

additional_tokens:
  - BNB
  - SOL
  - XRP

min_24h_volume_usd: 1000000

blacklist:
  - LUNC
  - USTC
EOF
    echo "✅ tokens.yml created"
fi

# Test database creation
echo ""
echo "💾 Testing database..."
python3 << 'PYEOF'
try:
    from src.services.database import DatabaseService
    db = DatabaseService()
    print('✅ Database ready')
except Exception as e:
    print(f'❌ Database error: {e}')
PYEOF

# Set permissions
echo ""
echo "🔐 Setting permissions..."
chmod +x main.py
chmod +x scripts/*.sh 2>/dev/null || true
echo "✅ Permissions set"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env with your API keys: nano .env"
echo "2. Edit config/config.yml if needed"
echo "3. Run: source venv/bin/activate"
echo "4. Run: python main.py test-connections"
echo "5. Run: python main.py start --test-mode"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"