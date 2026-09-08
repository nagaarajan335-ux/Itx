# Etsy + Redbubble Selling Kit

Everything you need to price, list, and launch a design on **Etsy** and
**Redbubble**. Fee math is verified against 2026 platform data (see sources at
the bottom of each file).

---

## ⚠️ Read this first: one blocker

Your product file **`hhgg4.pdf` never reached my workspace.** I checked
`/home/user/uploads/`, the entire filesystem, and the temp directories — it is
not there. The repo contained only a `README.md` reading `# Itx`.

**So every product-specific field below is a `{{PLACEHOLDER}}`.** The strategy,
fee math, specs, checklists, and templates are 100% real and finished. What I
cannot do until I see the artwork is: write your actual title, description, tag
list, and per-product prices.

**Re-send it one of these ways:**
1. Attach the PDF again (uploads sometimes fail silently).
2. Or attach the **source artwork** (`.png` / `.jpg` / `.svg` / `.ai` / `.psd`) —
   better, because a PDF is often the wrong format to *sell from* (see
   `04-file-specs-and-upload.md`).
3. Or just **describe it in chat**: what's depicted, the style, any text in it,
   and whether you drew it or generated it with AI. That's enough for me to fill
   in every placeholder.

Once I have it, I'll complete `product-profile.md` and generate finished,
copy-paste-ready listings for both platforms.

---

## What's in this kit

| File | What it gives you |
|---|---|
| `product-profile.md` | **Fill-in source of truth.** One page describing your product. Everything else derives from it. |
| `my-4-ideas.txt` | **Fill in your 4 ideas here**, then run the evaluator on it. Field guide included at the top of the file. |
| `idea-evaluator.py` | **Margin, profit and a WORKS / DOES NOT WORK verdict per idea**, with the specific reasons why. |
| `01-platform-comparison.md` | Etsy vs Redbubble head-to-head: fees, traffic, who wins on what, and the verdict on running both. |
| `02-pricing-and-profit.md` | Actual price points per product type, full fee math, worked examples, margin targets. |
| `03-listing-copy-templates.md` | Copy-paste title / description / attribute templates for both platforms. |
| `04-file-specs-and-upload.md` | Exact upload specs (px, DPI, formats, size caps) + step-by-step upload walkthroughs. |
| `05-keywords-and-tags.md` | Tag strategy, the 13-tag Etsy formula, the 15-tag Redbubble formula, keyword research method. |
| `06-launch-plan-30-days.md` | Day-by-day launch plan, marketing, and the first-sale playbook. |
| `07-legal-ip-tax.md` | Copyright, AI-content disclosure rules, trademarks, and tax/VAT basics. |
| `08-idea-viability-scorecard.md` | **Does your idea work, and if not why.** The 5 hard fails, 6 costly warnings, scoring model. |
| `profit-calculator.py` | **Working calculator.** Computes your exact profit per sale on both platforms. |

---

## Fastest path: evaluate your ideas

```bash
cd selling-kit

# 1. See which idea categories are worth pursuing at all
python3 idea-evaluator.py --types

# 2. Copy the template and fill in your 4 ideas
python3 idea-evaluator.py --template > my-4-ideas.txt

# 3. Get margin, profit and a verdict for all 4
python3 idea-evaluator.py my-4-ideas.txt
```

Or evaluate one idea without touching a file:

```bash
python3 idea-evaluator.py --quick "funny cat drinking coffee" \
        --type text-humor --resolution 4500 --competition high \
        --products sticker,tshirt,mug,digital
```

---

## Or start with the raw fee math

```bash
cd selling-kit

# Three worked examples
python3 profit-calculator.py demo

# Price YOUR product on Etsy
python3 profit-calculator.py etsy --price 24.99 --shipping 5.00 --cogs 11.50 --country us

# Price it on Redbubble
python3 profit-calculator.py redbubble --base 20.00 --markup 20 --tier standard

# Compare both platforms side by side
python3 profit-calculator.py matrix --product "classic t-shirt" --cogs 0

# Find the price that hits your profit goal
python3 profit-calculator.py etsy --price 20 --cogs 12 --solve --target-profit 8
```

No dependencies — plain Python 3. Run either tool with `--help`.

---

## The single most important thing in this kit

If you read nothing else, read this:

**Redbubble is a volume game with brutal per-unit economics. Etsy is a margin
game where you must bring your own traffic.**

On Redbubble's default **Standard** tier, a $24 t-shirt earns you **$2.00**.
That's not a typo — Redbubble takes its base price *and then* 50% of your
margin. You need hundreds of sales a month for it to matter.

The same design on Etsy via a print-on-demand partner earns roughly **$9–17**,
because you set the retail price and only pay ~11% in fees. But Etsy sends you
zero traffic unless your SEO is good or you pay for ads.

**Therefore:** Etsy is where your profit lives. Redbubble is free lottery
tickets — upload once, leave it running, and let its 16–25M monthly visitors
find you. Do both, but spend your effort where the margin is.

Full breakdown in `01-platform-comparison.md` and `02-pricing-and-profit.md`.
