#!/bin/bash
# Quick Security Fix for Heliox-AI
# Run this to generate secure secrets and create .env file

set -e

echo "🔒 HELIOX-AI SECURITY QUICK FIX"
echo "================================"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is required but not installed"
    exit 1
fi

# 1. Generate secure secrets
echo "📝 Generating secure secrets..."
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
ADMIN_API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
REDIS_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

# Check if cryptography is installed
if python3 -c "import cryptography" 2>/dev/null; then
    INTEGRATIONS_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
else
    echo "⚠️  Warning: cryptography not installed. Skipping INTEGRATIONS_ENCRYPTION_KEY"
    echo "   Install with: pip install cryptography"
    INTEGRATIONS_KEY=""
fi

# 2. Backup existing .env if it exists
if [ -f "backend/.env" ]; then
    echo "📦 Backing up existing .env to .env.backup.$(date +%Y%m%d_%H%M%S)"
    cp backend/.env "backend/.env.backup.$(date +%Y%m%d_%H%M%S)"
fi

# 3. Create .env file
echo "📄 Creating backend/.env..."
cat > backend/.env <<EOF
# ============================================
# HELIOX-AI PRODUCTION CONFIGURATION
# Generated: $(date)
# ============================================

# SECURITY - NEVER COMMIT THESE KEYS
SECRET_KEY=${SECRET_KEY}
ADMIN_API_KEY=${ADMIN_API_KEY}

# DATABASE
DB_USER=postgres
DB_PASSWORD=${DB_PASSWORD}
DATABASE_URL=postgresql+psycopg2://postgres:${DB_PASSWORD}@postgres:5432/heliox

# REDIS
REDIS_PASSWORD=${REDIS_PASSWORD}
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0

# APPLICATION
ENV=production
LOG_LEVEL=WARNING
MULTI_TENANT=true

# CORS - ⚠️ UPDATE WITH YOUR PRODUCTION DOMAINS
CORS_ENABLED=true
CORS_ORIGINS=["https://yourdomain.com","https://app.yourdomain.com"]

# INTEGRATIONS
INTEGRATIONS_ENCRYPTION_KEY=${INTEGRATIONS_KEY}

# RATE LIMITING (Production values)
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_MAX_REQUESTS=100

# USAGE METERING
USAGE_METERING_SAMPLE_RATE=1.0

# STRIPE (Optional - Add your keys)
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_ID_STARTER=
STRIPE_PRICE_ID_GROWTH=
STRIPE_PRICE_ID_ENTERPRISE=

# GOOGLE OAUTH (Optional - Add your credentials)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=https://yourdomain.com/api/v1/auth/google/callback
FRONTEND_URL=https://yourdomain.com

# SLACK NOTIFICATIONS (Optional)
SLACK_WEBHOOK_URL=
DAILY_SUMMARY_HOUR=9
TIMEZONE=UTC
EOF

echo "✅ .env file created at backend/.env"

# 4. Create .env for docker-compose
echo "📄 Creating .env for docker-compose..."
cat > .env <<EOF
# Docker Compose Environment Variables
POSTGRES_USER=postgres
POSTGRES_PASSWORD=${DB_PASSWORD}
POSTGRES_DB=heliox

REDIS_PASSWORD=${REDIS_PASSWORD}

# Build args
ENV=production
EOF

echo "✅ Root .env file created for docker-compose"

# 5. Verify .gitignore
echo "🔍 Checking .gitignore..."
if [ -f "backend/.gitignore" ]; then
    if ! grep -q "^\.env$" backend/.gitignore; then
        echo ".env" >> backend/.gitignore
        echo "✅ Added .env to backend/.gitignore"
    else
        echo "✅ .env already in backend/.gitignore"
    fi
else
    echo ".env" > backend/.gitignore
    echo "✅ Created backend/.gitignore with .env"
fi

if [ -f ".gitignore" ]; then
    if ! grep -q "^\.env$" .gitignore; then
        echo ".env" >> .gitignore
        echo "✅ Added .env to root .gitignore"
    else
        echo "✅ .env already in root .gitignore"
    fi
fi

# 6. Display summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎉 SECURITY FIXES APPLIED SUCCESSFULLY!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 GENERATED SECRETS:"
echo "   • SECRET_KEY:        ${SECRET_KEY:0:20}..."
echo "   • ADMIN_API_KEY:     ${ADMIN_API_KEY:0:20}..."
echo "   • DB_PASSWORD:       ${DB_PASSWORD:0:10}..."
echo "   • REDIS_PASSWORD:    ${REDIS_PASSWORD:0:10}..."
echo ""
echo "⚠️  CRITICAL: BEFORE DEPLOYMENT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. ✏️  Edit backend/.env:"
echo "   - Update CORS_ORIGINS with your domain(s)"
echo "   - Add Stripe keys if using billing"
echo "   - Add Google OAuth if using SSO"
echo ""
echo "2. 🐳 Update docker-compose.yml:"
echo "   - Remove hardcoded SECRET_KEY and ADMIN_API_KEY"
echo "   - Add 'env_file: - backend/.env' to services"
echo "   - Bind ports to 127.0.0.1 (not 0.0.0.0)"
echo ""
echo "3. 🔒 Verify secrets are not in git:"
echo "   git status  # Should NOT show .env files"
echo ""
echo "4. 🚀 Deploy:"
echo "   docker-compose down -v"
echo "   docker-compose up --build -d"
echo ""
echo "5. ✅ Test:"
echo "   curl http://localhost:8000/health"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📖 For full audit report, see: SECURITY_AUDIT_REPORT.md"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
