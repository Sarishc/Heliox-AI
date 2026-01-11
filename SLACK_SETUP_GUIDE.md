# Slack Setup Guide for Heliox Alerts

## 🎯 Quick Setup (5 minutes)

Follow these steps to set up Slack alerts for Heliox.

---

## Step 1: Create a Slack Test Channel

1. Open your Slack workspace
2. Click the **+** button next to "Channels"
3. Name it: `#heliox-alerts-test` (or your preferred name)
4. Make it **public** or **private** (your choice)
5. Click **Create**

---

## Step 2: Create Incoming Webhook

### Method A: Via Slack App (Recommended)

1. Go to: https://api.slack.com/messaging/webhooks
2. Click **"Create your Slack app"**
3. Select **"From scratch"**
4. App name: `Heliox Alerts`
5. Select your workspace
6. Click **"Create App"**

### Method B: Via Workspace Settings

1. Go to: `https://YOUR-WORKSPACE.slack.com/apps`
2. Search for **"Incoming Webhooks"**
3. Click **"Add to Slack"**
4. Select your test channel
5. Click **"Add Incoming WebHooks integration"**

---

## Step 3: Configure Webhook

After creating the app:

1. In the app settings, click **"Incoming Webhooks"**
2. Toggle **"Activate Incoming Webhooks"** to **ON**
3. Click **"Add New Webhook to Workspace"**
4. Select your `#heliox-alerts-test` channel
5. Click **"Allow"**
6. **Copy the Webhook URL** (looks like: `https://hooks.slack.com/services/T00000000/B00000000/XXXX...`)

---

## Step 4: Test Your Webhook

### Option A: Quick Test (curl)

```bash
curl -X POST YOUR_WEBHOOK_URL \
  -H 'Content-Type: application/json' \
  -d '{"text":"🎉 Heliox alerts are working!"}'
```

You should see a message in your Slack channel!

### Option B: Full Test Script (Recommended)

Run the comprehensive test script:

```bash
cd /Users/sarish/Downloads/Projects/Heliox-AI/backend
python3 test_slack_alerts.py
```

This will:
- Send 3 sample alerts (burn rate, idle spend, daily summary)
- Verify formatting
- Show you what real alerts will look like

---

## Step 5: Configure Heliox

Add the webhook URL to your `.env` file:

```bash
# In: /Users/sarish/Downloads/Projects/Heliox-AI/backend/.env

SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
DAILY_SUMMARY_HOUR=9
TIMEZONE=America/Los_Angeles
```

---

## Step 6: Start Celery (for scheduled alerts)

```bash
# Terminal 1: Start Celery worker
cd backend
celery -A app.celery_app worker --loglevel=info

# Terminal 2: Start Celery Beat scheduler
celery -A app.celery_app beat --loglevel=info
```

---

## 🎨 What to Expect

### 1. Burn Rate Alert 🔥

![Burn Rate Alert](docs/images/burn-rate-alert.png)

**Triggers:** When daily GPU spending exceeds $10,000

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

---

### 2. Idle Spend Alert ⚠️

![Idle Spend Alert](docs/images/idle-spend-alert.png)

**Triggers:** High-severity idle GPU recommendations detected

**Contains:**
- Total potential savings
- Number of issues
- Top 3 recommendations

**Example:**
```
⚠️ Idle GPU Spend Detected

High-severity idle spend recommendations found!

• Total Potential Savings: $2,376.00/month
• Number of Issues: 2

1. Idle GPU: H100 on AWS us-west-2
H100 GPU has been 100% idle for 14 days
💰 Savings: $1,176.00/month

2. Idle GPU: A100 on GCP us-central1
A100 GPU showing 100% idle time
💰 Savings: $1,200.00/month
```

---

### 3. Daily Summary 📊

![Daily Summary](docs/images/daily-summary.png)

**Triggers:** Every day at 9 AM (configurable)

**Contains:**
- Cost breakdown (yesterday, 7 days, 30 days)
- Top GPU consumers
- Recommendation count

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
• BERT-Large: $1,234.56

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ 2 high-severity recommendations available
Review them in your Heliox dashboard
```

---

## 🔧 Customization

### Change Alert Channel

To send alerts to a different channel:

1. Go to your Slack App settings
2. Click "Incoming Webhooks"
3. Click "Add New Webhook to Workspace"
4. Select the new channel
5. Update your `.env` with the new webhook URL

### Change Schedule

Edit `backend/app/celery_app.py`:

```python
celery_app.conf.beat_schedule = {
    "daily-summary": {
        "task": "app.tasks.slack_tasks.send_daily_summary_task",
        "schedule": crontab(hour=9, minute=0),  # Change time here
    },
    # ... other schedules
}
```

### Change Threshold

Edit `backend/app/services/slack_notifications.py`:

```python
BURN_RATE_THRESHOLD_USD = 10000  # Change threshold here
```

---

## 🚨 Troubleshooting

### Webhook not working?

1. **Test with curl:**
   ```bash
   curl -X POST $SLACK_WEBHOOK_URL \
     -H 'Content-Type: application/json' \
     -d '{"text":"Test"}'
   ```

2. **Check webhook is still active:**
   - Go to Slack App settings
   - Verify webhook URL hasn't been revoked

3. **Check channel permissions:**
   - Ensure the app has permission to post in the channel

### Messages not sending?

1. **Check Celery is running:**
   ```bash
   celery -A app.celery_app inspect active
   ```

2. **Check logs:**
   ```bash
   celery -A app.celery_app worker --loglevel=debug
   ```

3. **Check environment variable:**
   ```bash
   echo $SLACK_WEBHOOK_URL
   ```

---

## 📚 Additional Resources

- [Slack Incoming Webhooks Docs](https://api.slack.com/messaging/webhooks)
- [Slack Block Kit Builder](https://app.slack.com/block-kit-builder) (for customization)
- [Celery Documentation](https://docs.celeryproject.org/)

---

## ✅ Checklist

- [ ] Created Slack test channel
- [ ] Created Incoming Webhook
- [ ] Tested webhook with curl
- [ ] Ran `test_slack_alerts.py` script
- [ ] Verified all 3 alert types format correctly
- [ ] Added webhook URL to `.env`
- [ ] Started Celery worker
- [ ] Started Celery Beat scheduler
- [ ] Alerts are working! 🎉

---

## 🎊 You're Done!

Your Slack alerts are now configured and will send automatically based on the schedule.

**Need help?** Check `SLACK_ALERTING_README.md` for detailed documentation.

