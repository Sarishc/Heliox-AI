"""Test script for Slack alerts - sends sample messages to verify formatting."""
import asyncio
import sys
from datetime import date, timedelta

# Add parent directory to path
sys.path.insert(0, '/Users/sarish/Downloads/Projects/Heliox-AI/backend')

from app.services.slack_notifications import SlackNotificationService


async def test_burn_rate_alert(webhook_url: str):
    """Test burn rate alert formatting."""
    print("\n" + "="*80)
    print("Testing: 🔥 High Burn Rate Alert")
    print("="*80)
    
    service = SlackNotificationService(webhook_url=webhook_url)
    
    success = await service.send_burn_rate_alert(
        daily_cost=15234.56,
        threshold=10000.00,
        date="2026-01-09"
    )
    
    if success:
        print("✅ Burn rate alert sent successfully!")
        print("Check your Slack channel for a message with:")
        print("  - 🔥 High Burn Rate Alert header")
        print("  - Daily cost: $15,234.56")
        print("  - Threshold: $10,000.00")
        print("  - Over by: $5,234.56 (52.3%)")
    else:
        print("❌ Failed to send burn rate alert")
    
    return success


async def test_idle_spend_alert(webhook_url: str):
    """Test idle spend alert formatting."""
    print("\n" + "="*80)
    print("Testing: ⚠️ Idle Spend Alert")
    print("="*80)
    
    service = SlackNotificationService(webhook_url=webhook_url)
    
    recommendations = [
        {
            "title": "Idle GPU: H100 on AWS us-west-2",
            "description": "H100 GPU has been 100% idle for 14 days. This represents wasted compute capacity and ongoing costs.",
            "estimated_savings_usd": 1176.00,
            "severity": "high"
        },
        {
            "title": "Idle GPU: A100 on GCP us-central1",
            "description": "A100 GPU showing 100% idle time over the past 7 days with zero job executions.",
            "estimated_savings_usd": 1200.00,
            "severity": "high"
        }
    ]
    
    success = await service.send_idle_spend_alert(recommendations)
    
    if success:
        print("✅ Idle spend alert sent successfully!")
        print("Check your Slack channel for a message with:")
        print("  - ⚠️ Idle GPU Spend Detected header")
        print("  - Total savings: $2,376.00/month")
        print("  - 2 recommendations with details")
    else:
        print("❌ Failed to send idle spend alert")
    
    return success


async def test_daily_summary(webhook_url: str):
    """Test daily summary formatting."""
    print("\n" + "="*80)
    print("Testing: 📊 Daily Summary")
    print("="*80)
    
    service = SlackNotificationService(webhook_url=webhook_url)
    
    top_models = [
        {"model_name": "Stable Diffusion XL", "cost": 5123.45},
        {"model_name": "GPT-4", "cost": 3456.78},
        {"model_name": "BERT-Large", "cost": 1234.56}
    ]
    
    success = await service.send_daily_summary(
        daily_cost=11234.56,
        weekly_cost=78456.78,
        monthly_cost=324567.89,
        top_models=top_models,
        high_severity_count=2,
        total_savings=2376.00
    )
    
    if success:
        print("✅ Daily summary sent successfully!")
        print("Check your Slack channel for a message with:")
        print("  - 📊 Heliox Daily Summary header")
        print("  - Cost breakdown (yesterday, 7 days, 30 days)")
        print("  - Top 3 GPU consumers")
        print("  - Recommendations summary")
    else:
        print("❌ Failed to send daily summary")
    
    return success


async def main():
    """Main test function."""
    print("\n" + "╔" + "="*78 + "╗")
    print("║" + " "*78 + "║")
    print("║" + "  🧪 SLACK ALERT FORMATTING TEST  ".center(78) + "║")
    print("║" + " "*78 + "║")
    print("╚" + "="*78 + "╝")
    
    # Get webhook URL from user
    print("\n📝 Instructions:")
    print("   1. Go to your Slack workspace")
    print("   2. Create a test channel (e.g., #heliox-alerts-test)")
    print("   3. Go to https://api.slack.com/messaging/webhooks")
    print("   4. Click 'Create New App' → 'From scratch'")
    print("   5. Name it 'Heliox Alerts' and select your workspace")
    print("   6. Click 'Incoming Webhooks' → Enable it")
    print("   7. Click 'Add New Webhook to Workspace'")
    print("   8. Select your test channel")
    print("   9. Copy the webhook URL\n")
    
    webhook_url = input("🔗 Enter your Slack webhook URL: ").strip()
    
    if not webhook_url:
        print("❌ No webhook URL provided. Exiting.")
        return
    
    if not webhook_url.startswith("https://hooks.slack.com/"):
        print("⚠️  Warning: URL doesn't look like a Slack webhook URL")
        proceed = input("   Continue anyway? (y/n): ").strip().lower()
        if proceed != 'y':
            return
    
    print("\n🚀 Starting tests...")
    print("   This will send 3 test messages to your Slack channel")
    input("   Press Enter to continue...")
    
    # Run tests
    results = []
    
    # Test 1: Burn Rate Alert
    results.append(await test_burn_rate_alert(webhook_url))
    await asyncio.sleep(2)  # Pause between messages
    
    # Test 2: Idle Spend Alert
    results.append(await test_idle_spend_alert(webhook_url))
    await asyncio.sleep(2)
    
    # Test 3: Daily Summary
    results.append(await test_daily_summary(webhook_url))
    
    # Summary
    print("\n" + "="*80)
    print("📊 TEST RESULTS SUMMARY")
    print("="*80)
    
    test_names = ["Burn Rate Alert", "Idle Spend Alert", "Daily Summary"]
    for i, (name, success) in enumerate(zip(test_names, results), 1):
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{i}. {name}: {status}")
    
    passed = sum(results)
    total = len(results)
    
    print(f"\n{'✅' if passed == total else '⚠️'} {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All alerts formatted correctly!")
        print("   Check your Slack channel to verify the formatting.")
        print("\n📝 Next steps:")
        print("   1. Add webhook URL to your .env file:")
        print(f"      SLACK_WEBHOOK_URL={webhook_url}")
        print("   2. Restart your backend services")
        print("   3. Alerts will be sent automatically based on schedule")
    else:
        print("\n⚠️ Some tests failed. Check the error messages above.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

