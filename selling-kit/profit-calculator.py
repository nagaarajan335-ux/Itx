#!/usr/bin/env python3
"""
Etsy + Redbubble profit calculator.

Computes exactly what lands in your pocket per sale on both platforms using
verified 2026 fee structures. No dependencies -- plain Python 3.

USAGE
    python3 profit-calculator.py demo
    python3 profit-calculator.py etsy      --price 6.00 --cogs 0 --country us
    python3 profit-calculator.py redbubble --base 20.00 --markup 20 --tier standard
    python3 profit-calculator.py etsy      --price 6.00 --target-profit 3.50 --solve
    python3 profit-calculator.py matrix    --product "wall art print"

FEE SOURCES (as of 2026-09-08)
  Etsy       $0.20 listing + 6.5% transaction (on item + shipping) + payment
             processing (US 3% + $0.25; UK 4% + GBP0.20; EU 4% + EUR0.30)
             + optional offsite ads 15% (under $10k/yr) or 12% (over),
             capped at $100 per order + 2.5% currency conversion.
  Redbubble  retail = base_price x (1 + markup%). Your gross margin is
             base_price x markup%. Platform fee on that margin: Standard 50%,
             Premium 20%, Pro 0%, capped at $150 per payment period.
             Excess markup fee: 50% of margin earned ABOVE a 20% markup
             (Standard/Premium only).
"""

import argparse
import sys

# --------------------------------------------------------------------------- #
# Fee tables
# --------------------------------------------------------------------------- #

# Etsy Payments processing fee by seller country: (percent, flat, currency)
ETSY_PROCESSING = {
    "us": (0.030, 0.25, "USD"),
    "uk": (0.040, 0.20, "GBP"),
    "eu": (0.040, 0.30, "EUR"),
    "ca": (0.030, 0.25, "CAD"),
    "au": (0.030, 0.25, "AUD"),
    "in": (0.045, 20.00, "INR"),   # approx; confirm in your Payment account
    "other": (0.040, 0.30, "LOCAL"),
}

ETSY_LISTING_FEE = 0.20          # per listing / per unit sold
ETSY_TRANSACTION_FEE = 0.065     # on item price + shipping + gift wrap
ETSY_CURRENCY_CONVERSION = 0.025
ETSY_OFFSITE_ADS = {"none": 0.0, "under10k": 0.15, "over10k": 0.12}
ETSY_OFFSITE_ADS_CAP = 100.00

# Redbubble
RB_PLATFORM_FEE = {"standard": 0.50, "premium": 0.20, "pro": 0.0}
RB_EXCESS_MARKUP_THRESHOLD = 0.20   # 20% markup
RB_EXCESS_MARKUP_FEE = 0.50         # 50% of margin above the threshold
RB_PLATFORM_FEE_CAP = 150.00        # per payment period

# Typical Redbubble base prices, USD, mid-size option. VERIFY in your own
# dashboard: base price changes with product size AND the buyer's country, and
# Redbubble revises them periodically. Read the real number from the
# "Edit products" screen when you upload -- then pass it with --base.
RB_BASE_PRICES = {
    "sticker (small)":      1.99,   # retail lands ~$2.40-$3.60 at 20-80% markup
    "sticker (large)":      2.51,
    "essential t-shirt":   17.50,
    "classic t-shirt":     20.00,
    "premium t-shirt":     24.00,
    "hoodie":              40.00,
    "mug 11oz":            13.00,
    "art print (small)":   13.50,
    "art print (large)":   24.00,
    "poster":              19.00,
    "phone case":          18.00,
    "tote bag":            16.00,
    "notebook":            13.00,
    "throw pillow":        20.00,
    "mouse pad":           15.00,
}

# Realistic Etsy retail bands for the same product types (what buyers pay).
ETSY_RETAIL_BANDS = {
    "sticker":            (3.00, 5.50),
    "digital download":   (3.50, 9.00),
    "t-shirt":            (21.00, 29.00),
    "mug":                (15.00, 22.00),
    "art print (phys)":   (18.00, 45.00),
    "phone case":         (20.00, 30.00),
    "tote bag":           (18.00, 26.00),
    "hoodie":             (40.00, 60.00),
}


def money(x):
    return f"${x:,.2f}"


# --------------------------------------------------------------------------- #
# Etsy
# --------------------------------------------------------------------------- #

def etsy_fees(price, shipping=0.0, giftwrap=0.0, tax=0.0, country="us",
              offsite="none", currency_conversion=False, regulatory=0.0):
    """Return (line_items dict, total_fees, order_total)."""
    pct, flat, cur = ETSY_PROCESSING.get(country, ETSY_PROCESSING["other"])

    order_total = price + shipping + giftwrap
    # Processing is charged on the buyer's full total, tax included.
    processing_base = order_total + tax

    lines = {
        "Listing fee": ETSY_LISTING_FEE,
        "Transaction fee (6.5%)": order_total * ETSY_TRANSACTION_FEE,
        f"Payment processing ({pct:.1%} + {flat:.2f} {cur})":
            processing_base * pct + flat,
    }

    if regulatory:
        lines[f"Regulatory op. fee ({regulatory:.2%})"] = order_total * regulatory

    if currency_conversion:
        lines["Currency conversion (2.5%)"] = order_total * ETSY_CURRENCY_CONVERSION

    ad_rate = ETSY_OFFSITE_ADS[offsite]
    if ad_rate:
        lines[f"Offsite Ads ({ad_rate:.0%})"] = min(order_total * ad_rate,
                                                    ETSY_OFFSITE_ADS_CAP)

    total = sum(lines.values())
    return lines, total, order_total


def etsy_report(args):
    lines, fees, order_total = etsy_fees(
        args.price, args.shipping, args.giftwrap, args.tax,
        args.country, args.offsite, args.fx, args.regulatory,
    )
    revenue = args.price + args.shipping
    profit = revenue - fees - args.cogs

    print("\n" + "=" * 64)
    print("ETSY PROFIT BREAKDOWN")
    print("=" * 64)
    print(f"Item price            {money(args.price)}")
    if args.shipping:
        print(f"Shipping charged      {money(args.shipping)}")
    if args.giftwrap:
        print(f"Gift wrap charged     {money(args.giftwrap)}")
    print(f"Order total           {money(order_total)}")
    print("-" * 64)
    for k, v in lines.items():
        print(f"  - {k:<42}{money(v)}")
    print("-" * 64)
    print(f"TOTAL ETSY FEES       {money(fees)}"
          f"   ({fees / order_total:.1%} of order)")
    if args.cogs:
        print(f"Your product cost     {money(args.cogs)}")
    print(f"NET PROFIT PER SALE   {money(profit)}"
          f"   ({profit / revenue:.1%} margin on item price)")
    if profit <= 0:
        print("\n  !! WARNING: you LOSE money on this listing.")
    elif profit / max(revenue, 0.01) < 0.30:
        print("\n  ! Thin margin (<30%). Consider raising price or cutting COGS.")
    print("=" * 64)

    if args.solve:
        solve_etsy_price(args)


def solve_etsy_price(args):
    """Find the item price needed to hit --target-profit."""
    lo, hi = 0.01, 10000.0
    for _ in range(200):
        mid = (lo + hi) / 2
        _, fees, _ = etsy_fees(mid, args.shipping, args.giftwrap, args.tax,
                               args.country, args.offsite, args.fx,
                               args.regulatory)
        profit = (mid + args.shipping) - fees - args.cogs
        if profit < args.target_profit:
            lo = mid
        else:
            hi = mid
    price = hi
    print(f"\nTo clear {money(args.target_profit)} profit per sale "
          f"(COGS {money(args.cogs)}, shipping {money(args.shipping)}):")
    print(f"   --> price the item at {money(round(price * 100) / 100)} "
          f"(round to {money(round_to_pretty(price))})")


def round_to_pretty(x):
    """Round up to a buyer-friendly price point."""
    candidates = [x + 0.99 - (x % 1) if x % 1 else x + 0.99,
                  round(x) + 0.95, round(x) + 0.99, round(x) + 0.50,
                  round(x / 5.0 + 0.5) * 5.0]
    valid = [c for c in candidates if c >= x]
    return min(valid) if valid else round(x, 2)


# --------------------------------------------------------------------------- #
# Redbubble
# --------------------------------------------------------------------------- #

def redbubble_earnings(base, markup, tier="standard"):
    markup = markup / 100.0 if markup > 1 else markup
    retail = base * (1 + markup)
    gross_margin = base * markup

    excess = 0.0
    if tier in ("standard", "premium") and markup > RB_EXCESS_MARKUP_THRESHOLD:
        above = gross_margin - base * RB_EXCESS_MARKUP_THRESHOLD
        excess = above * RB_EXCESS_MARKUP_FEE

    adjusted = gross_margin - excess
    platform = min(adjusted * RB_PLATFORM_FEE[tier], RB_PLATFORM_FEE_CAP)
    net = adjusted - platform

    return {
        "base": base, "markup": markup, "retail": retail,
        "gross_margin": gross_margin, "excess": excess,
        "adjusted": adjusted, "platform": platform, "net": net,
    }


def redbubble_report(args):
    r = redbubble_earnings(args.base, args.markup, args.tier)

    print("\n" + "=" * 64)
    print(f"REDBUBBLE PROFIT BREAKDOWN  (tier: {args.tier.upper()})")
    print("=" * 64)
    print(f"Base price (RB cost)      {money(r['base'])}")
    print(f"Your markup               {r['markup']:.0%}")
    print(f"Retail price buyer pays   {money(r['retail'])}")
    print("-" * 64)
    print(f"  Gross artist margin     {money(r['gross_margin'])}")
    if r["excess"]:
        print(f"  - Excess markup fee     {money(r['excess'])}"
              f"   (50% of margin above 20%)")
        print(f"  = Adjusted margin       {money(r['adjusted'])}")
    label = f"  - Platform fee ({RB_PLATFORM_FEE[args.tier]:.0%})"
    print(f"{label:<42}{money(r['platform'])}")
    print("-" * 64)
    print(f"  NET TO YOU PER SALE     {money(r['net'])}"
          f"   ({r['net'] / r['retail']:.1%} of retail)")
    print("=" * 64)

    if r["markup"] > RB_EXCESS_MARKUP_THRESHOLD and args.tier != "pro":
        print(f"\n  ! You are above the 20% markup threshold and paying the")
        print(f"    excess markup fee. Compare with 20%:")
        r20 = redbubble_earnings(args.base, 20, args.tier)
        print(f"    at 20% markup -> {money(r20['net'])}/sale "
              f"(retail {money(r20['retail'])})")
        print(f"    at {r['markup']:.0%} markup -> {money(r['net'])}/sale "
              f"(retail {money(r['retail'])})")
        print(f"    difference: {money(r['net'] - r20['net'])}")


# --------------------------------------------------------------------------- #
# Comparison matrix
# --------------------------------------------------------------------------- #

def matrix_report(args):
    print("\n" + "=" * 78)
    print(f"CROSS-PLATFORM COMPARISON{': ' + args.product if args.product else ''}")
    print("=" * 78)

    key = (args.product or "").lower()
    rb_key = next((k for k in RB_BASE_PRICES if key.startswith(k.split(" (")[0])),
                  None)
    etsy_key = next((k for k in ETSY_RETAIL_BANDS if key.startswith(k.split(" ")[0])),
                    None)
    base = RB_BASE_PRICES.get(rb_key, args.base)
    lo, hi = ETSY_RETAIL_BANDS.get(etsy_key, (args.price, args.price))

    print("\nREDBUBBLE -- earnings at each markup (Standard tier, the default)\n")
    print(f"{'markup':>7} | {'retail':>9} | {'gross':>7} | "
          f"{'excess':>7} | {'plat fee':>8} | {'YOU GET':>8}")
    print("-" * 62)
    for mk in (10, 15, 20, 25, 30, 40, 50):
        r = redbubble_earnings(base, mk, args.tier)
        print(f"{mk:>6}% | {money(r['retail']):>9} | "
              f"{money(r['gross_margin']):>7} | {money(r['excess']):>7} | "
              f"{money(r['platform']):>8} | {money(r['net']):>8}")

    print(f"\nREDBUBBLE -- same at 20% markup across all three tiers\n")
    print(f"{'tier':>10} | {'platform fee':>12} | {'YOU GET':>8} | {'% of retail':>11}")
    print("-" * 50)
    for tier in ("standard", "premium", "pro"):
        r = redbubble_earnings(base, 20, tier)
        print(f"{tier:>10} | {RB_PLATFORM_FEE[tier]:>11.0%} | "
              f"{money(r['net']):>8} | {r['net']/r['retail']:>10.1%}")

    print(f"\nETSY -- profit at each price point "
          f"(COGS {money(args.cogs)}, {args.country.upper()})\n")
    print(f"{'price':>8} | {'etsy fees':>10} | {'eff. rate':>9} | {'PROFIT':>8}")
    print("-" * 46)
    prices = [lo, (lo + hi) / 2, hi] if hi > lo else [args.price]
    prices += [p for p in (2.99, 4.99, 9.99, 14.99, 24.99, 34.99)
               if p not in prices]
    for p in sorted(set(round(x, 2) for x in prices)):
        _, fees, ot = etsy_fees(p, args.shipping, country=args.country,
                                offsite=args.offsite)
        profit = (p + args.shipping) - fees - args.cogs
        print(f"{money(p):>8} | {money(fees):>10} | {fees/ot:>8.1%} | "
              f"{money(profit):>8}")
    print("=" * 78)


def demo(_args):
    print("\n### WORKED EXAMPLE 1 -- $6.00 digital download on Etsy (US seller)")
    lines, fees, ot = etsy_fees(6.00, country="us")
    for k, v in lines.items():
        print(f"   {k:<44}{money(v)}")
    print(f"   {'TOTAL FEES':<44}{money(fees)}  ({fees/ot:.1%})")
    print(f"   {'PROFIT (no COGS)':<44}{money(6.00 - fees)}")

    print("\n### WORKED EXAMPLE 2 -- Classic tee on Redbubble, 20% markup")
    for tier in ("standard", "premium", "pro"):
        r = redbubble_earnings(20.00, 20, tier)
        print(f"   {tier.upper():<10} retail {money(r['retail']):<8} "
              f"-> you get {money(r['net'])}")

    print("\n### WORKED EXAMPLE 3 -- Same tee, 30% markup, Standard tier")
    r = redbubble_earnings(20.00, 30, "standard")
    print(f"   gross margin {money(r['gross_margin'])} "
          f"- excess fee {money(r['excess'])} = {money(r['adjusted'])}")
    print(f"   - platform fee (50%) {money(r['platform'])} "
          f"-> you get {money(r['net'])}")
    print("   ^ raising markup 20%->30% earned you "
          f"{money(r['net'] - redbubble_earnings(20.0, 20, 'standard')['net'])}"
          " extra while pushing retail from $24.00 to $26.00")
    print()


# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser(
        description="Etsy + Redbubble profit calculator (2026 fee structures)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("USAGE")[1].split("FEE SOURCES")[0]
        if "USAGE" in __doc__ else None,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--country", default="us",
                        choices=sorted(ETSY_PROCESSING),
                        help="your seller country (sets processing fee)")
    common.add_argument("--offsite", default="none",
                        choices=sorted(ETSY_OFFSITE_ADS),
                        help="assume an Offsite Ads-attributed sale?")
    common.add_argument("--cogs", type=float, default=0.0,
                        help="your cost of goods (POD production, materials)")
    common.add_argument("--tier", default="standard",
                        choices=sorted(RB_PLATFORM_FEE),
                        help="Redbubble account tier")

    d = sub.add_parser("demo", help="run three worked examples")
    d.set_defaults(func=demo)

    e = sub.add_parser("etsy", parents=[common], help="Etsy breakdown")
    e.add_argument("--price", type=float, required=True, help="item price")
    e.add_argument("--shipping", type=float, default=0.0,
                   help="shipping you charge the buyer")
    e.add_argument("--giftwrap", type=float, default=0.0)
    e.add_argument("--tax", type=float, default=0.0,
                   help="sales tax collected (processing fee applies to it)")
    e.add_argument("--regulatory", type=float, default=0.0,
                   help="regulatory operating fee rate, e.g. 0.004 for 0.4%%")
    e.add_argument("--fx", action="store_true",
                   help="buyer pays in a different currency (adds 2.5%%)")
    e.add_argument("--solve", action="store_true",
                   help="also solve for the price hitting --target-profit")
    e.add_argument("--target-profit", type=float, default=None)
    e.set_defaults(func=etsy_report)

    r = sub.add_parser("redbubble", parents=[common], help="Redbubble breakdown")
    r.add_argument("--base", type=float, required=True,
                   help="Redbubble base price for the product")
    r.add_argument("--markup", type=float, required=True,
                   help="your markup percent, e.g. 20")
    r.set_defaults(func=redbubble_report)

    m = sub.add_parser("matrix", parents=[common],
                       help="side-by-side comparison across markups/prices")
    m.add_argument("--product", default="", help="e.g. 'sticker', 'classic t-shirt'")
    m.add_argument("--base", type=float, default=20.0)
    m.add_argument("--price", type=float, default=24.99)
    m.add_argument("--shipping", type=float, default=0.0)
    m.set_defaults(func=matrix_report)

    args = ap.parse_args()
    if args.cmd == "etsy" and args.solve and args.target_profit is None:
        ap.error("--solve requires --target-profit")
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
