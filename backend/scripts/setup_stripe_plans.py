#!/usr/bin/env python3
"""
One-time (idempotent) Stripe product and price setup for Heliox.

Creates:
  - Growth product + $199/month recurring price
  - Enterprise product (no price — custom/contact sales)

Idempotency: looks up existing products and prices by name before creating.
Running this script twice is safe — it will find existing objects and skip.

Usage:
  STRIPE_SECRET_KEY=sk_... python scripts/setup_stripe_plans.py

Output:
  Prints the Price IDs to add to .env:
    STRIPE_PRICE_ID_GROWTH=price_...
    STRIPE_PRICE_ID_ENTERPRISE=  (contact sales, no Stripe price)

Stores price IDs in Stripe product metadata for self-documentation.
"""
from __future__ import annotations

import os
import sys

import stripe

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
if not STRIPE_SECRET_KEY:
    print("ERROR: STRIPE_SECRET_KEY environment variable is required", file=sys.stderr)
    sys.exit(1)

stripe.api_key = STRIPE_SECRET_KEY

PLANS = [
    {
        "name": "Heliox Growth",
        "description": "GPU cost visibility for ML teams — up to 5 clusters, 365-day history, Slack alerts, API access.",
        "price_usd_cents": 19900,  # $199.00
        "interval": "month",
        "metadata": {
            "plan": "growth",
            "max_clusters": "5",
            "history_days": "365",
            "max_api_keys": "5",
            "slack_alerts": "true",
            "sso_enabled": "false",
        },
    },
    {
        "name": "Heliox Enterprise",
        "description": "Unlimited clusters, SSO (SAML + Google), custom RBAC, dedicated CSM. Contact sales.",
        "price_usd_cents": None,  # custom — no Stripe price
        "interval": None,
        "metadata": {
            "plan": "enterprise",
            "max_clusters": "unlimited",
            "sso_enabled": "true",
            "custom_rbac": "true",
            "dedicated_csm": "true",
        },
    },
]


def find_product_by_name(name: str) -> stripe.Product | None:
    """Return existing Stripe product matching name, or None."""
    products = stripe.Product.list(limit=100, active=True)
    for product in products.auto_paging_iter():
        if product.name == name:
            return product
    return None


def find_price_for_product(product_id: str, unit_amount: int, interval: str) -> stripe.Price | None:
    """Return existing recurring price for a product, or None."""
    prices = stripe.Price.list(product=product_id, active=True, limit=20)
    for price in prices.data:
        if (
            price.unit_amount == unit_amount
            and price.recurring
            and price.recurring.interval == interval
            and price.currency == "usd"
        ):
            return price
    return None


def setup_plan(plan: dict) -> tuple[str, str | None]:
    """
    Ensure product (and price, if applicable) exists in Stripe.

    Returns (product_id, price_id_or_None).
    """
    name = plan["name"]

    # --- Product ---
    product = find_product_by_name(name)
    if product:
        print(f"  Found existing product: {name} ({product.id})")
    else:
        product = stripe.Product.create(
            name=name,
            description=plan["description"],
            metadata=plan["metadata"],
        )
        print(f"  Created product: {name} ({product.id})")

    # --- Price (paid plans only) ---
    price_id = None
    if plan["price_usd_cents"] is not None:
        price = find_price_for_product(product.id, plan["price_usd_cents"], plan["interval"])
        if price:
            print(f"  Found existing price: ${plan['price_usd_cents'] / 100:.2f}/{plan['interval']} ({price.id})")
            price_id = price.id
        else:
            price = stripe.Price.create(
                product=product.id,
                unit_amount=plan["price_usd_cents"],
                currency="usd",
                recurring={"interval": plan["interval"]},
                metadata={"plan": plan["metadata"]["plan"]},
            )
            print(f"  Created price: ${plan['price_usd_cents'] / 100:.2f}/{plan['interval']} ({price.id})")
            price_id = price.id

        # Store price ID back in product metadata for self-documentation
        stripe.Product.modify(product.id, metadata={**plan["metadata"], "stripe_price_id": price_id})

    return product.id, price_id


def main() -> None:
    print("Heliox Stripe plan setup")
    print(f"Using key: {STRIPE_SECRET_KEY[:12]}...")
    print()

    results: dict[str, str | None] = {}

    for plan in PLANS:
        plan_key = plan["metadata"]["plan"]
        print(f"Setting up {plan['name']}...")
        _product_id, price_id = setup_plan(plan)
        results[plan_key] = price_id
        print()

    print("=" * 60)
    print("Add these to your .env / ECS task definition:")
    print()
    growth_price = results.get("growth") or ""
    print(f"STRIPE_PRICE_ID_GROWTH={growth_price}")
    print("STRIPE_PRICE_ID_ENTERPRISE=  # contact sales — no Stripe price")
    print()
    print("Webhook events to enable in Stripe Dashboard → Developers → Webhooks:")
    print("  customer.subscription.created")
    print("  customer.subscription.updated")
    print("  customer.subscription.deleted")
    print("  invoice.paid")
    print("  invoice.payment_failed")
    print("  checkout.session.completed")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
