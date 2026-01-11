# Heliox Slack Alerting

Production-ready Slack notification system for GPU cost monitoring and optimization alerts.

## 🎯 Overview

Heliox can automatically send Slack notifications for:
1. **High Burn Rate Alerts** - When daily GPU spending exceeds threshold
2. **Idle Spend Alerts** - When high-severity idle GPU recommendations are found
3. **Daily Summaries** - Morning reports with cost breakdown and recommendations

## 🚀 Quick Start

### 1. Set Up Slack Webhook

1. Go to your Slack workspace settings
2. Navigate to **Apps** → **Incoming Webhooks**
3. Click **Add to Slack**
4. Select a channel for notifications
5. Copy the webhook URL (looks like: `https://hooks.slack.com/services/T00000000/B00000000/XXXX`)

### 2. Configure Environment Variables

Add to your `.env` file:

```bash
# Required: Slack Webhook URL
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Optional: Alert Configuration
DAILY_SUMMARY_HOUR=9        # Hour to send daily summary (0-23)
TIMEZONE=America/Los_Angeles # Your local timezone
```

### 3. Start Celery Workers

In production, you need both a Celery worker and Celery Beat scheduler:

```bash
# Terminal 1: Start Celery worker
cd backend
celery -A app.celery_app worker --loglevel=info

# Terminal 2: Start Celery Beat scheduler
celery -A app.celery_app beat --loglevel=info
```

### 4. Verify Setup

Check that notifications are enabled:

```bash
# Should show "Slack notifications enabled"
docker-compose logs api | grep -i slack
```

## 📊 Alert Types

### 1. High Burn Rate Alert 🔥

**Triggered when:** Daily GPU spending exceeds $10,000 (configurable)

**Schedule:** Checked every hour (8 AM - 8 PM)

**Contains:**
- Daily cost vs threshold
- Percentage over budget
- Date of high spend

**Example:**
```
🔥 High Burn Rate Alert

Daily GPU spending has exceeded the threshold!

• Date: 2026-01-09
• Daily Cost: $15,234.56
• Threshold: $10,000.00
• Over by: $5,234.56 (52.3%)

💡 Review your GPU usage to identify cost drivers
```

### 2. Idle Spend Alert ⚠️

**Triggered when:** High-severity idle GPU recommendations are detected

**Schedule:** Checked twice daily (10 AM, 4 PM)

**Contains:**
- Total potential savings
- Number of issues
- Top 3 recommendations with details

**Example:**
```
⚠️ Idle GPU Spend Detected

High-severity idle spend recommendations found!

• Total Potential Savings: $2,376.00/month
• Number of Issues: 2

1. Idle GPU: H100 on AWS
100% idle for 14 days
💰 Savings: $1,176.00/month

2. Idle GPU: A100 on GCP
100% idle for 7 days
💰 Savings: $1,200.00/month
```

### 3. Daily Summary 📊

**Triggered when:** Every day at configured hour (default: 9 AM)

**Schedule:** Once daily

**Contains:**
- Yesterday's cost
- Last 7 days cost
- Last 30 days cost
- Top GPU consuming models
- High-severity recommendation count
- Total potential savings

**Example:**
```
📊 Heliox Daily Summary

Yesterday:          Last 7 Days:
$11,234.56         $78,456.78

Last 30 Days:       Potential Savings:
$324,567.89        $2,376.00/mo

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Top GPU Consumers (Yesterday):
• Stable Diffusion XL: $5,123.45
• GPT-4: $3,456.78
• BERT: $1,234.56

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ 2 high-severity recommendations available
Review them in your Heliox dashboard
```

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SLACK_WEBHOOK_URL` | None | Slack Incoming Webhook URL (required) |
| `DAILY_SUMMARY_HOUR` | 9 | Hour (0-23) to send daily summary |
| `TIMEZONE` | UTC | Timezone for scheduled tasks |

### Alert Thresholds

Edit `backend/app/services/slack_notifications.py`:

```python
# Daily spend threshold for burn rate alerts (USD)
BURN_RATE_THRESHOLD_USD = 10000  # Change as needed
```

### Schedule Configuration

Edit `backend/app/celery_app.py`:

```python
celery_app.conf.beat_schedule = {
    "daily-summary": {
        "task": "app.tasks.slack_tasks.send_daily_summary_task",
        "schedule": crontab(hour=9, minute=0),  # Customize time
    },
    "check-burn-rate": {
        "task": "app.tasks.slack_tasks.check_burn_rate_task",
        "schedule": crontab(hour="8-20", minute=0),  # Every hour 8AM-8PM
    },
    "check-idle-spend": {
        "task": "app.tasks.slack_tasks.check_idle_spend_task",
        "schedule": crontab(hour="10,16", minute=0),  # 10AM and 4PM
    },
}
```

## 🛠️ Development

### Run Celery Locally

```bash
# Install dependencies
cd backend
pip install -r requirements.txt

# Start worker
celery -A app.celery_app worker --loglevel=info

# Start beat scheduler (in separate terminal)
celery -A app.celery_app beat --loglevel=info

# Monitor with Flower (optional)
celery -A app.celery_app flower
# Visit http://localhost:5555
```

### Test Alerts Manually

```python
# In Python shell
from app.core.db import SessionLocal
from app.services.slack_notifications import (
    check_and_send_burn_rate_alert,
    check_and_send_idle_spend_alert,
    send_daily_summary_report
)
import asyncio

db = SessionLocal()

# Test burn rate alert
asyncio.run(check_and_send_burn_rate_alert(db))

# Test idle spend alert
asyncio.run(check_and_send_idle_spend_alert(db))

# Test daily summary
asyncio.run(send_daily_summary_report(db))

db.close()
```

### Run Tests

```bash
cd backend
pytest tests/test_slack_notifications.py -v
```

## 🚨 Production Deployment

### Docker Compose

Add Celery services to `docker-compose.yml`:

```yaml
celery-worker:
  build: ./backend
  command: celery -A app.celery_app worker --loglevel=info
  depends_on:
    - postgres
    - redis
  environment:
    - DATABASE_URL=postgresql://heliox:heliox_password@postgres:5432/heliox
    - REDIS_URL=redis://redis:6379/0
    - SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}
  volumes:
    - ./backend:/app

celery-beat:
  build: ./backend
  command: celery -A app.celery_app beat --loglevel=info
  depends_on:
    - postgres
    - redis
  environment:
    - DATABASE_URL=postgresql://heliox:heliox_password@postgres:5432/heliox
    - REDIS_URL=redis://redis:6379/0
    - SLACK_WEBHOOK_URL=${SLACK_WEBHOOK_URL}
    - TIMEZONE=America/Los_Angeles
  volumes:
    - ./backend:/app
```

### Kubernetes

See `k8s/celery-deployment.yaml` for example Kubernetes configuration.

### Monitoring

Use **Flower** to monitor Celery tasks:

```bash
# Start Flower
celery -A app.celery_app flower

# Visit dashboard
open http://localhost:5555
```

## 🔒 Security

### Webhook URL Safety

- ✅ Webhook URLs are **never logged** in plain text
- ✅ Only last 8 characters shown in logs (masked)
- ✅ Stored securely in environment variables
- ✅ Not committed to version control

### Retry & Timeout

- ✅ **Max 3 retries** with exponential backoff
- ✅ **10-second timeout** per request
- ✅ **5-minute task timeout** for Celery tasks
- ✅ Safe error handling and logging

## 📋 Troubleshooting

### Alerts Not Sending

1. **Check webhook URL is configured:**
   ```bash
   echo $SLACK_WEBHOOK_URL
   ```

2. **Check Celery worker is running:**
   ```bash
   celery -A app.celery_app inspect active
   ```

3. **Check Celery logs:**
   ```bash
   celery -A app.celery_app worker --loglevel=debug
   ```

4. **Test webhook manually:**
   ```bash
   curl -X POST $SLACK_WEBHOOK_URL \
     -H 'Content-Type: application/json' \
     -d '{"text":"Test from Heliox"}'
   ```

### No Data for Alerts

- Ensure you have seeded demo data:
  ```bash
  curl -X POST http://localhost:8000/api/v1/admin/demo/seed \
    -H "X-API-Key: heliox-admin-key-change-in-production"
  ```

### Timezone Issues

- Set correct timezone in `.env`:
  ```bash
  TIMEZONE=America/Los_Angeles  # or your timezone
  ```
- Use `pytz` timezone names (e.g., `US/Pacific`, `Europe/London`)

## 🎊 Summary

Heliox Slack Alerting provides:

- ✅ **3 types of alerts** (burn rate, idle spend, daily summary)
- ✅ **Automated scheduling** via Celery Beat
- ✅ **Configurable thresholds and times**
- ✅ **Retry logic and timeouts**
- ✅ **Secure webhook handling**
- ✅ **Beautiful Slack formatting** with Block Kit
- ✅ **Production-ready** deployment

Stay on top of your GPU costs with real-time Slack notifications! 🚀

