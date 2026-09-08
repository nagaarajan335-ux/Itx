#!/usr/bin/env python3
"""
Idea viability evaluator for Etsy + Redbubble.

Answers two questions for any product/design idea:
  1. What margin and profit do I actually make, on both platforms?
  2. Does this idea WORK -- and if not, exactly why not?

USAGE
    # Evaluate the 4 ideas in a spec file (this is what you want)
    python3 idea-evaluator.py my-4-ideas.txt

    # Evaluate one idea quickly from the command line
    python3 idea-evaluator.py --quick "funny cat drinking coffee mug quote" \
            --type text-humor --resolution 4500 --products sticker,tshirt,mug,digital

    # Start from a template you can edit
    python3 idea-evaluator.py --template > my-4-ideas.txt

    # Show the idea-type reference table (demand / competition / best platform)
    python3 idea-evaluator.py --types

Exit codes: 0 = all ideas viable, 1 = at least one idea fails.
"""

import argparse
import importlib.util
import os
import sys

# Reuse the verified fee math from profit-calculator.py ---------------------- #
_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "pc", os.path.join(_HERE, "profit-calculator.py"))
pc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pc)


# --------------------------------------------------------------------------- #
# Idea-type taxonomy: realistic market assumptions per category.
# demand/competition are 1-10 (competition 10 = brutally saturated).
# --------------------------------------------------------------------------- #
IDEA_TYPES = {
    "text-humor": {
        "label": "Funny text / quote / meme",
        "demand": 8, "competition": 8, "ip_risk": 6,
        "best": "Redbubble",
        "products": ["sticker", "tshirt", "mug", "hoodie"],
        "note": "Impulse buys. Redbubble's browsing audience loves these. "
                "HUGE IP trap: quotes, lyrics and slogans are often trademarked.",
    },
    "minimalist-line-art": {
        "label": "Minimalist line art",
        "demand": 7, "competition": 6, "ip_risk": 1,
        "best": "Etsy",
        "products": ["digital", "artprint", "tshirt", "mug"],
        "note": "Strong Etsy digital-download category. Easy to make variants.",
    },
    "botanical-vintage": {
        "label": "Vintage botanical / scientific illustration",
        "demand": 7, "competition": 5, "ip_risk": 2,
        "best": "Etsy",
        "products": ["digital", "artprint", "tote", "notebook"],
        "note": "Evergreen. Public-domain source material exists -- but scan "
                "quality must be genuinely restored by you to be defensible.",
    },
    "illustration-art": {
        "label": "Original illustration / character art",
        "demand": 6, "competition": 6, "ip_risk": 3,
        "best": "Both",
        "products": ["sticker", "digital", "artprint", "tshirt", "phonecase"],
        "note": "Stickers are the entry point; builds a following for the rest.",
    },
    "pattern-seamless": {
        "label": "Seamless pattern / surface design",
        "demand": 5, "competition": 4, "ip_risk": 1,
        "best": "Redbubble",
        "products": ["duvet", "pillow", "tote", "phonecase", "notebook"],
        "note": "The ONLY idea type that works on full-bleed products. "
                "Redbubble home decor is a real market for this.",
    },
    "photographic": {
        "label": "Photography",
        "demand": 5, "competition": 7, "ip_risk": 1,
        "best": "Etsy",
        "products": ["digital", "artprint", "metalprint"],
        "note": "Poor fit for stickers/apparel. Needs very high resolution.",
    },
    "niche-hobby": {
        "label": "Niche hobby / profession (birds, fishing, nursing, D&D...)",
        "demand": 6, "competition": 3, "ip_risk": 2,
        "best": "Etsy",
        "products": ["sticker", "tshirt", "mug", "digital"],
        "note": "BEST category for a new shop. Low competition, high intent, "
                "long-tail keywords you can actually rank for.",
    },
    "seasonal": {
        "label": "Seasonal / holiday",
        "demand": 9, "competition": 9, "ip_risk": 4,
        "best": "Both",
        "products": ["sticker", "tshirt", "mug", "digital"],
        "note": "Massive spikes, then zero. Must list 6-8 weeks early. "
                "Avoid trademarked holiday characters entirely.",
    },
    "personalized": {
        "label": "Personalised / custom (names, monograms, pets)",
        "demand": 8, "competition": 5, "ip_risk": 1,
        "best": "Etsy",
        "products": ["digital", "mug", "artprint", "tshirt"],
        "note": "Etsy's highest-converting category. Requires per-order work, "
                "but buyers pay a premium and competition is weaker.",
    },
    "abstract": {
        "label": "Abstract / geometric",
        "demand": 4, "competition": 8, "ip_risk": 1,
        "best": "Etsy",
        "products": ["digital", "artprint"],
        "note": "Extremely saturated and hard to differentiate. Needs a strong "
                "colour/trend angle to stand out.",
    },
}

# Product economics: (etsy_retail, etsy_cogs, redbubble_base, ships_via_pod)
PRODUCTS = {
    "digital":    {"label": "Digital download",  "etsy": 7.99,  "cogs": 0.00,
                   "rb": None,  "ship": 0.0},
    "digital-bundle": {"label": "Digital bundle", "etsy": 19.99, "cogs": 0.00,
                       "rb": None, "ship": 0.0},
    "sticker":    {"label": "Sticker",           "etsy": 4.99,  "cogs": 1.60,
                   "rb": 1.99, "ship": 0.0, "rb_markup": 50},
    "tshirt":     {"label": "T-shirt",           "etsy": 24.99, "cogs": 13.50,
                   "rb": 20.00, "ship": 5.0, "rb_markup": 20},
    "hoodie":     {"label": "Hoodie",            "etsy": 54.99, "cogs": 30.00,
                   "rb": 40.00, "ship": 7.0, "rb_markup": 20},
    "mug":        {"label": "Mug 11oz",          "etsy": 19.99, "cogs": 9.50,
                   "rb": 13.00, "ship": 5.0, "rb_markup": 20},
    "artprint":   {"label": "Art print (POD)",   "etsy": 28.99, "cogs": 12.00,
                   "rb": 19.00, "ship": 6.0, "rb_markup": 20},
    "phonecase":  {"label": "Phone case",        "etsy": 26.99, "cogs": 12.00,
                   "rb": 18.00, "ship": 4.0, "rb_markup": 20},
    "tote":       {"label": "Tote bag",          "etsy": 22.99, "cogs": 11.00,
                   "rb": 16.00, "ship": 4.0, "rb_markup": 20},
    "notebook":   {"label": "Notebook",          "etsy": 19.99, "cogs": 9.50,
                   "rb": 13.00, "ship": 4.0, "rb_markup": 20},
    "pillow":     {"label": "Throw pillow",      "etsy": 32.99, "cogs": 16.00,
                   "rb": 20.00, "ship": 6.0, "rb_markup": 20},
    "duvet":      {"label": "Duvet / blanket",   "etsy": 89.99, "cogs": 55.00,
                   "rb": 60.00, "ship": 10.0, "rb_markup": 20},
    "metalprint": {"label": "Metal print",       "etsy": 59.99, "cogs": 32.00,
                   "rb": 30.00, "ship": 8.0, "rb_markup": 20},
}

RB_DEFAULT_MARKUP = 20

# Accept these spellings so a mistyped product name doesn't get silently
# dropped from the evaluation.
PRODUCT_ALIASES = {
    "digitalbundle": "digital-bundle",
    "bundle": "digital-bundle",
    "digitalpack": "digital-bundle",
    "tee": "tshirt",
    "shirt": "tshirt",
    "tshirt": "tshirt",
    "tshirts": "tshirt",
    "tees": "tshirt",
    "shirt": "tshirt",
    "print": "artprint",
    "artprints": "artprint",
    "poster": "artprint",
    "case": "phonecase",
    "phonecases": "phonecase",
    "mugs": "mug",
    "stickers": "sticker",
    "hoodies": "hoodie",
    "sweatshirt": "hoodie",
    "totebag": "tote",
    "totes": "tote",
    "notebooks": "notebook",
    "journal": "notebook",
    "pillows": "pillow",
    "throwpillow": "pillow",
    "blanket": "duvet",
    "duvetcover": "duvet",
    "metal": "metalprint",
    "metalprints": "metalprint",
    "digitaldownload": "digital",
    "download": "digital",
    "digitals": "digital",
}


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
TEMPLATE = """# ============================================================================
# MY IDEAS -- edit this file, then run:
#     python3 idea-evaluator.py my-4-ideas.txt
#
# Every field except `name` is optional; sensible defaults are applied.
# ============================================================================

# --- Idea 1 -----------------------------------------------------------------
name = Funny cat drinking coffee quote
type = text-humor
resolution_px = 4500
ip_risk = low
ai_assisted = no
competition = high
products = sticker,tshirt,mug,digital
country = us
etsy_ship_charged = 5.00
rb_tier = standard

# --- Idea 2 -----------------------------------------------------------------
name = Minimalist heron line art
type = minimalist-line-art
resolution_px = 5000
ip_risk = none
ai_assisted = no
competition = medium
products = digital,artprint,tshirt
country = us

# --- Idea 3 -----------------------------------------------------------------
name = Vintage wildflower botanical set
type = botanical-vintage
resolution_px = 4000
ip_risk = none
ai_assisted = yes
competition = medium
products = digital,artprint,tote
country = us

# --- Idea 4 -----------------------------------------------------------------
name = Seamless mushroom forest pattern
type = pattern-seamless
resolution_px = 7000
ip_risk = none
ai_assisted = no
competition = low
products = pillow,duvet,tote,phonecase
country = us
"""


def parse_file(path):
    ideas, cur = [], None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = (x.strip() for x in line.split("=", 1))
            k = k.lower()
            if k == "name":
                cur = {"name": v}
                ideas.append(cur)
            elif cur is not None:
                cur[k] = v
    return ideas


def _num(d, key, default):
    try:
        return float(str(d.get(key, default)).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return default


def normalise(idea):
    t = idea.get("type", "").lower().strip()
    if t not in IDEA_TYPES:
        t = "illustration-art"
    meta = IDEA_TYPES[t]

    prods_raw = idea.get("products", "")
    requested = [p.strip().lower().replace(" ", "")
                 for p in prods_raw.split(",") if p.strip()]
    products, unknown = [], []
    for p in requested:
        resolved = p if p in PRODUCTS else PRODUCT_ALIASES.get(p)
        if resolved and resolved in PRODUCTS:
            if resolved not in products:
                products.append(resolved)
        else:
            unknown.append(p)
    if not products:
        products = list(meta["products"])

    ipr = str(idea.get("ip_risk", "")).lower()
    ip_score = {"none": 0, "low": 3, "medium": 6, "high": 9}.get(
        ipr, min(10, meta["ip_risk"]))

    comp = str(idea.get("competition", "")).lower()
    comp_score = {"low": 2, "medium": 5, "high": 8, "brutal": 10}.get(
        comp, meta["competition"])

    return {
        "name": idea.get("name") or "Untitled idea",
        "type": t,
        "meta": meta,
        "products": products,
        "resolution": _num(idea, "resolution_px", 4500),
        "ip_score": ip_score,
        "competition": comp_score,
        "ai": str(idea.get("ai_assisted", "no")).lower() in
              ("yes", "y", "true", "1"),
        "country": idea.get("country", "us").lower(),
        "ship_charged": _num(idea, "etsy_ship_charged", 5.0),
        "rb_tier": str(idea.get("rb_tier", "standard")).lower(),
        "price_override": idea.get("etsy_price"),
        "unknown_products": unknown,
    }


# --------------------------------------------------------------------------- #
# Economics
# --------------------------------------------------------------------------- #
def economics(idea):
    """Per-product profit on each platform."""
    rows = []
    for key in idea["products"]:
        p = PRODUCTS[key]

        # Etsy
        price = _num({"x": idea["price_override"]}, "x", p["etsy"]) \
            if idea["price_override"] else p["etsy"]
        ship = idea["ship_charged"] if p["ship"] else 0.0
        _, fees, ot = pc.etsy_fees(price, shipping=ship, country=idea["country"])
        etsy_profit = (price + ship) - fees - p["cogs"]
        etsy_margin = etsy_profit / max(price, 0.01)

        # Redbubble
        rb = None
        if p["rb"]:
            mk = p.get("rb_markup", RB_DEFAULT_MARKUP)
            r = pc.redbubble_earnings(p["rb"], mk, idea["rb_tier"])
            rb = {"markup": mk, "retail": r["retail"], "net": r["net"],
                  "pct_of_retail": r["net"] / r["retail"]}

        rows.append({"key": key, "label": p["label"], "etsy_price": price,
                     "etsy_fees": fees, "etsy_cogs": p["cogs"],
                     "etsy_profit": etsy_profit, "etsy_margin": etsy_margin,
                     "rb": rb})
    return rows


def best_channel(rows):
    """Which platform wins, and by how much."""
    e = sum(r["etsy_profit"] for r in rows)
    b = sum(r["rb"]["net"] for r in rows if r["rb"])
    if b == 0:
        return "etsy", e, b
    return ("etsy" if e / max(len(rows), 1) > b / max(
        len([r for r in rows if r["rb"]]), 1) else "redbubble"), e, b


# --------------------------------------------------------------------------- #
# Verdict logic -- the "does it work, and if not WHY" engine
# --------------------------------------------------------------------------- #
def diagnose(idea, rows):
    hard_fails, warnings, wins = [], [], []

    name = idea["name"]
    res = idea["resolution"]

    # ---- HARD FAILS (idea does not work as described) ----
    if idea["ip_score"] >= 8:
        hard_fails.append((
            "IP / trademark risk is HIGH.",
            "Both platforms run automated IP scanners. Characters, brand logos, "
            "celebrity likenesses, song lyrics and team names trigger a takedown "
            "PLUS a strike. Enough strikes = permanent suspension with your "
            "earnings frozen. This is the #1 cause of POD account death.\n"
            "     FIX: remove every protected element, or abandon the idea. "
            "Check your phrases at tmsearch.uspto.gov (classes 16, 25, 35)."))

    if res < 1500:
        hard_fails.append((
            f"Master file is only {res:.0f}px -- far too small to print.",
            "You cannot add detail that isn't there; upscaling invents blur. "
            "At this resolution even a sticker prints soft, and wall art or "
            "apparel is impossible. Redbubble will show a quality warning.\n"
            "     FIX: rebuild from the original vector, re-render/re-draw at "
            "5000x5500px, or drop to digital-only at small print sizes."))

    cheap = [r for r in rows if r["etsy_price"] < 4.0 and r["etsy_cogs"] > 0]
    if cheap:
        hard_fails.append((
            "You are pricing a physical product under $4.00 on Etsy.",
            "Etsy's flat fees ($0.20 listing + $0.25 processing) make this "
            "structurally unprofitable. A $2.99 item loses ~25% to fees before "
            "you pay for materials or postage -- you will lose money per sale.\n"
            "     FIX: bundle 5 units at $9.99, or raise the price. "
            "See the price-floor table in 02-pricing-and-profit.md."))

    if "reselling" in name.lower() or "bundle pack bought" in name.lower():
        hard_fails.append((
            "This is not your own work.",
            "Reselling a downloaded design or an 'AI art pack' as your own "
            "violates both platforms' terms regardless of how it was made.\n"
            "     FIX: create original work."))

    if idea["ai"] and res < 2000 and not hard_fails:
        hard_fails.append((
            "AI-assisted output at low resolution.",
            "Generators typically output 1024-2048px. That is fine for stickers, "
            "too small for apparel and wall art.\n"
            "     FIX: use a proper upscaler (Topaz, Real-ESRGAN) THEN redraw "
            "or repaint key areas, or re-generate at high resolution."))

    # ---- WARNINGS (works, but will underperform) ----
    if idea.get("unknown_products"):
        warnings.append((
            "Unrecognised product name(s) in your spec: "
            f"{', '.join(idea['unknown_products'])}",
            "These were skipped, so your numbers cover fewer products than you "
            "intended. Valid names: " + ", ".join(sorted(PRODUCTS)) + ".\n"
            "     FIX: correct the spelling in the `products =` line."))

    if 1500 <= res < 3600:
        warnings.append((
            f"Resolution {res:.0f}px is borderline.",
            "Usable for stickers, mugs and phone cases. Wall prints, hoodies "
            "and full-bleed products will print soft. Redbubble may flag it.\n"
            "     FIX: limit product types, or rebuild the master at 5000px+."))

    if idea["competition"] >= 8:
        warnings.append((
            "This niche is heavily saturated.",
            "A new shop with zero reviews cannot out-rank sellers with 40,000 "
            "sales on a head term like 'wall art' or 'funny shirt'. You will "
            "get impressions but no clicks.\n"
            "     FIX: attack a long-tail angle instead -- profession, hobby, "
            "room, colourway or region. See 05-keywords-and-tags.md."))

    if idea["competition"] >= 8 and idea["type"] == "abstract":
        warnings.append((
            "Abstract art is the hardest category to differentiate.",
            "Buyers have infinite near-identical options and no reason to pick "
            "yours.\n     FIX: pick a named colour trend (sage, terracotta, "
            "japandi) and target it explicitly in title and tags."))

    if all(r["key"] == "sticker" for r in rows):
        warnings.append((
            "Stickers only.",
            f"On Redbubble Standard tier a sticker nets ~$0.20-0.60. You need "
            f"34-101 sticker sales just to clear the $20 payout threshold. On "
            f"Etsy a $4.99 sticker nets ~$2.20 after materials and postage.\n"
            "     FIX: keep stickers as the traffic/review builder, but add "
            "t-shirts, mugs or digital downloads where the real margin is."))

    if not any(r["key"].startswith("digital") for r in rows):
        warnings.append((
            "No digital download version.",
            "Digital is the highest-margin product that exists: $7.99 costs "
            "you $1.21 in fees and $0 in production = 85% margin, instant "
            "delivery, no shipping, no returns, no inventory. Skipping it "
            "leaves the best money on the table for the same artwork.\n"
            "     FIX: export ratio-pack ZIPs and list it as a digital download "
            "alongside the physical versions."))

    if idea["type"] == "seasonal":
        warnings.append((
            "Seasonal ideas have a hard launch deadline.",
            "Search volume peaks 4-6 weeks before the holiday, then collapses "
            "to zero. Listing in-season means you arrive after the buyers.\n"
            "     FIX: list 6-8 weeks early. Etsy needs 2-4 weeks to index a "
            "new listing before it ranks at all."))

    if idea["type"] == "pattern-seamless" and not any(
            r["key"] in ("duvet", "pillow", "tote") for r in rows):
        warnings.append((
            "A seamless pattern isn't being used on full-bleed products.",
            "Patterns are the ONLY artwork type that looks right on duvet "
            "covers, blankets and shower curtains -- and those are the "
            "highest-ticket items on Redbubble.\n"
            "     FIX: enable the full-bleed home products."))

    if idea["type"] == "photographic" and any(
            r["key"] in ("sticker", "tshirt") for r in rows):
        warnings.append((
            "Photography performs poorly on stickers and apparel.",
            "Photos need rectangular print areas and rarely suit garment "
            "placement; conversion is weak.\n"
            "     FIX: focus on wall art, metal prints and digital downloads."))

    if idea["ai"]:
        warnings.append((
            "AI-assisted work carries mandatory disclosure duties.",
            "ETSY: must be categorised 'Designed by a seller' (never 'Made by'), "
            "and AI use must be disclosed in the description. Prompt-only "
            "bundles are prohibited. REDBUBBLE: tick the AI disclosure box "
            "(shown publicly as 'Creation Info'); new accounts are capped at "
            "~5 AI uploads/day, and mass-uploading raw output triggers spam "
            "filters that can pin you in Standard tier permanently.\n"
            "     FIX: make substantial human edits -- compositing, repainting, "
            "original typography, colour grading. This also gives you a "
            "defensible copyright claim, which pure AI output does not have."))

    # NOTE: the Redbubble Standard-tier 50% fee is a universal platform fact,
    # not a defect of any particular idea -- so it is reported separately as a
    # standing reality check and deliberately does NOT lower the verdict score.

    # ---- WINS ----
    if idea["competition"] <= 3:
        wins.append("Low competition -- a new shop can genuinely rank for this.")
    if idea["ip_score"] <= 1:
        wins.append("Clean IP position -- no takedown or strike risk.")
    if idea["type"] in ("niche-hobby", "personalized"):
        wins.append(f"{idea['meta']['label']} is one of the best categories "
                    f"for a new shop: specific intent, weaker competition, "
                    f"long-tail keywords you can win.")
    if any(r["key"].startswith("digital") for r in rows):
        wins.append("Includes a digital download -- highest margin available.")
    if res >= 5000:
        wins.append(f"Resolution {res:.0f}px is excellent -- every product type "
                    f"including 24x36\" wall art is viable.")
    if len(rows) >= 4:
        wins.append(f"{len(rows)} product types -- one design, multiple "
                    f"revenue streams, no extra artwork needed.")

    # ---- SCORE ----
    demand = idea["meta"]["demand"]
    comp = 10 - idea["competition"]
    margins = [r["etsy_margin"] for r in rows if r["etsy_price"] > 0]
    margin_score = max(0, min(10, sum(margins) / len(margins) * 12)) if margins else 3
    scale_score = min(10, len(rows) * 1.8)
    ip_score = 10 - idea["ip_score"]

    overall = round((demand + comp + margin_score + scale_score + ip_score) / 5, 1)

    if hard_fails:
        verdict, icon = "DOES NOT WORK", "X"
    elif overall >= 7 and not warnings:
        verdict, icon = "WORKS", "OK"
    elif overall >= 5.5:
        verdict, icon = "WORKS WITH FIXES", "~"
    else:
        verdict, icon = "WEAK -- REWORK IT", "!"

    return {"hard_fails": hard_fails, "warnings": warnings, "wins": wins,
            "scores": {"demand": demand, "competition": comp,
                       "margin": round(margin_score, 1),
                       "scale": round(scale_score, 1), "ip": ip_score,
                       "overall": overall},
            "verdict": verdict, "icon": icon}


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def m(x):
    return f"${x:,.2f}"


def bar(n, width=10):
    filled = int(round(n))
    return "#" * filled + "." * (width - filled)


def report(idea, rows, dx, index=None, total=None):
    W = 78
    hdr = f"IDEA{f' {index}/{total}' if index else ''}: {idea['name']}"
    print("\n" + "=" * W)
    print(hdr[:W])
    print(f"{idea['meta']['label']}   |   master {idea['resolution']:.0f}px"
          f"   |   Redbubble tier: {idea['rb_tier']}")
    print("=" * W)
    print(f"\nVERDICT: [{dx['icon']}] {dx['verdict']}")

    # --- Margin per sale ---
    print("\nMARGIN AND PROFIT PER SALE")
    print("-" * W)
    print(f"{'product':<20}{'ETSY':^30}{'REDBUBBLE':^26}")
    print(f"{'':<20}{'price':>8}{'fees':>8}{'PROFIT':>8}{'mgn':>6}"
          f"{'retail':>8}{'PROFIT':>8}{'mgn':>7}{'  ':>3}")
    print("-" * W)
    for r in rows:
        rb = r["rb"]
        rb_str = (f"{m(rb['retail']):>8}{m(rb['net']):>8}"
                  f"{rb['pct_of_retail']:>6.1%}") if rb else f"{'n/a':>23}"
        flag = "  <<< LOSS" if r["etsy_profit"] <= 0 else (
               "  << thin" if r["etsy_margin"] < 0.30 and r["etsy_cogs"] > 0 else "")
        print(f"{r['label']:<20}{m(r['etsy_price']):>8}{m(r['etsy_fees']):>8}"
              f"{m(r['etsy_profit']):>8}{r['etsy_margin']:>6.0%}"
              f"{rb_str}{flag}")
    print("-" * W)

    etsy_avg = sum(r["etsy_profit"] for r in rows) / max(len(rows), 1)
    rb_rows = [r for r in rows if r["rb"]]
    rb_avg = sum(r["rb"]["net"] for r in rb_rows) / max(len(rb_rows), 1)
    ratio = etsy_avg / rb_avg if rb_avg else float("inf")
    print(f"Average profit per sale:  ETSY {m(etsy_avg)}   "
          f"REDBUBBLE {m(rb_avg)}   -> Etsy pays {ratio:.1f}x more")

    # --- Monthly projection ---
    best = max(rows, key=lambda r: r["etsy_profit"])
    print("\nMONTHLY PROJECTION  (selling the best product in this idea)")
    print(f"  best product: {best['label']} at {m(best['etsy_price'])} "
          f"-> {m(best['etsy_profit'])}/sale on Etsy")
    print("-" * W)
    print(f"{'sales/month':>12}{'ETSY':>14}{'REDBUBBLE':>14}{'COMBINED':>14}"
          f"{'per day':>12}")
    print("-" * W)
    rb_best = best["rb"]["net"] if best["rb"] else 0.0
    for n in (5, 10, 25, 50, 100, 250):
        e, b = best["etsy_profit"] * n, rb_best * n
        print(f"{n:>12}{m(e):>14}{m(b):>14}{m(e + b):>14}{m((e+b)/30):>12}")
    print("-" * W)
    print("  Redbubble needs no customer service, no shipping and no "
          "inventory -- it is genuinely passive.")
    print("  Etsy needs SEO, mockups, 10 photos and support. That is why it "
          "pays more.")

    # --- Scorecard ---
    s = dx["scores"]
    print("\nVIABILITY SCORECARD")
    print("-" * W)
    for label, val, hi in (("Demand", s["demand"], 10),
                           ("Competition (10=easy)", s["competition"], 10),
                           ("Margin", s["margin"], 10),
                           ("Scalability", s["scale"], 10),
                           ("IP safety", s["ip"], 10)):
        print(f"  {label:<24}{bar(val):<12}{val:>4}/10")
    print(f"  {'OVERALL':<24}{bar(s['overall']):<12}{s['overall']:>4}/10")

    # --- Standing platform reality (not idea-specific, not scored) ---
    print("\nPLATFORM REALITY (applies to every idea, not scored)")
    print("-" * W)
    if idea["rb_tier"] == "standard":
        print("  * Redbubble Standard tier takes 50% of your margin. It is the")
        print("    default for every new account and promotion is by invitation")
        print("    only, using undisclosed criteria. Assume you stay here.")
        print("    Do NOT raise markup above 20% to compensate -- the excess")
        print("    markup fee claws back half the gain.")
        print("  * Etsy takes ~11% of a sale and pays 3-7x more per unit,")
        print("    but sends you zero traffic unless your SEO works.")
    else:
        print(f"  * Redbubble tier: {idea['rb_tier']} "
              f"({pc.RB_PLATFORM_FEE[idea['rb_tier']]:.0%} platform fee).")

    # --- Reasons ---
    if dx["hard_fails"]:
        print("\n" + "!" * W)
        print("WHY IT DOES NOT WORK")
        print("!" * W)
        for i, (title, detail) in enumerate(dx["hard_fails"], 1):
            print(f"\n  {i}. {title}")
            for line in detail.split("\n"):
                print(f"     {line}")
    if dx["warnings"]:
        print("\nPROBLEMS THAT WILL COST YOU MONEY (fixable)")
        print("-" * W)
        for i, (title, detail) in enumerate(dx["warnings"], 1):
            print(f"\n  {i}. {title}")
            for line in detail.split("\n"):
                print(f"     {line}")
    if dx["wins"]:
        print("\nWHAT IS WORKING IN YOUR FAVOUR")
        print("-" * W)
        for w in dx["wins"]:
            print(f"  + {w}")

    print("\nRECOMMENDED PLAY")
    print("-" * W)
    if dx["hard_fails"]:
        print("  Do not launch until the failures above are resolved.")
    else:
        best_plat = "Etsy" if etsy_avg >= rb_avg else "Redbubble"
        print(f"  1. Lead with {best_plat} -- it pays {ratio:.1f}x more per sale."
              if ratio != float("inf") else "  1. Lead with Etsy (digital only).")
        print(f"  2. Build the master file at 5000x5500px / 300 DPI / sRGB.")
        print(f"  3. List on Etsy first: "
              f"{', '.join(r['label'] for r in rows[:4])}.")
        print(f"  4. Upload the same master to Redbubble, markup 20% "
              f"(stickers 50-100%).")
        print(f"  5. Make 3-5 colourway/variant listings from this one design.")
    print("=" * W)


def types_table():
    print("\n" + "=" * 92)
    print("IDEA-TYPE REFERENCE -- demand, competition and best platform")
    print("=" * 92)
    print(f"{'type':<22}{'demand':>8}{'compet.':>9}{'IP risk':>9}"
          f"{'best':>12}   default products")
    print("-" * 92)
    for k, v in IDEA_TYPES.items():
        print(f"{k:<22}{v['demand']:>6}/10{v['competition']:>7}/10"
              f"{v['ip_risk']:>7}/10{v['best']:>12}   "
              f"{','.join(v['products'][:4])}")
    print("-" * 92)
    print("\nNOTES\n")
    for k, v in IDEA_TYPES.items():
        print(f"  {k}")
        print(f"     {v['note']}\n")
    print("IP risk 10 = near-certain takedown/strike. Competition 10 = a new")
    print("shop cannot rank. Demand 10 = very high search volume.")
    print("=" * 92)


def main():
    ap = argparse.ArgumentParser(
        description="Evaluate margin, profit and viability of product ideas "
                    "for Etsy + Redbubble",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?",
                    help="spec file with your ideas (see --template)")
    ap.add_argument("--template", action="store_true",
                    help="print an editable 4-idea template to stdout")
    ap.add_argument("--types", action="store_true",
                    help="print the idea-type reference table")
    ap.add_argument("--quick", metavar="NAME",
                    help="evaluate a single idea by name")
    ap.add_argument("--type", default="illustration-art",
                    choices=sorted(IDEA_TYPES))
    ap.add_argument("--resolution", type=float, default=4500)
    ap.add_argument("--ip-risk", default=None,
                    choices=["none", "low", "medium", "high"])
    ap.add_argument("--ai", action="store_true")
    ap.add_argument("--competition", default=None,
                    choices=["low", "medium", "high", "brutal"])
    ap.add_argument("--products", default="")
    ap.add_argument("--country", default="us")
    ap.add_argument("--rb-tier", default="standard",
                    choices=["standard", "premium", "pro"])
    args = ap.parse_args()

    if args.template:
        print(TEMPLATE)
        return 0
    if args.types:
        types_table()
        return 0

    if args.quick:
        raw = [{"name": args.quick, "type": args.type,
                "resolution_px": args.resolution,
                "ip_risk": args.ip_risk or "",
                "ai_assisted": "yes" if args.ai else "no",
                "competition": args.competition or "",
                "products": args.products, "country": args.country,
                "rb_tier": args.rb_tier}]
    elif args.file:
        if not os.path.exists(args.file):
            ap.error(f"no such file: {args.file}")
        raw = parse_file(args.file)
        if not raw:
            ap.error("no ideas found. Each idea needs a `name = ...` line.")
    else:
        ap.print_help()
        print("\nNothing to do. Try:  python3 idea-evaluator.py --template "
              "> my-4-ideas.txt")
        return 0

    ideas = [normalise(i) for i in raw]
    failed = 0
    for idx, idea in enumerate(ideas, 1):
        rows = economics(idea)
        dx = diagnose(idea, rows)
        report(idea, rows, dx, idx, len(ideas))
        if dx["hard_fails"]:
            failed += 1

    if len(ideas) > 1:
        print("\n" + "#" * 78)
        print("SUMMARY -- all ideas ranked")
        print("#" * 78)
        scored = []
        for idea in ideas:
            rows = economics(idea)
            dx = diagnose(idea, rows)
            best = max(r["etsy_profit"] for r in rows)
            scored.append((dx["scores"]["overall"], idea["name"], dx["verdict"],
                           best, dx["hard_fails"]))
        for overall, nm, verdict, best, hf in sorted(scored, reverse=True):
            flag = "  <<< FIX BEFORE LAUNCH" if hf else ""
            print(f"  {overall:>4}/10  {nm[:38]:<40}{verdict:<18}"
                  f"best {m(best)}/sale{flag}")
        print("#" * 78)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
