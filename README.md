# Itx

Selling kit for launching artwork on **Etsy** and **Redbubble** — pricing,
listing copy, file specs, keywords, launch plan, and a working profit calculator.

## ⚠️ Status

The product file `hhgg4.pdf` was attached in chat but **did not reach the
workspace**, so every product-specific field is still a `{{PLACEHOLDER}}`. The
strategy, fee math, specs and templates are complete and verified against 2026
platform data. Re-send the artwork (or just describe it) and the placeholders
get filled in.

## Contents

Everything lives in [`selling-kit/`](selling-kit/):

| File | What it is |
|---|---|
| [`README.md`](selling-kit/README.md) | Index, the blocker, and the 10-minute quick start |
| [`my-4-ideas.txt`](selling-kit/my-4-ideas.txt) | **Fill your 4 ideas in here**, then run the evaluator |
| [`idea-evaluator.py`](selling-kit/idea-evaluator.py) | Margin + profit + WORKS/DOES NOT WORK verdict per idea |
| [`08-idea-viability-scorecard.md`](selling-kit/08-idea-viability-scorecard.md) | The 5 reasons an idea fails, and the 6 costly warnings |
| [`product-profile.md`](selling-kit/product-profile.md) | Fill-in source of truth — everything else derives from it |
| [`01-platform-comparison.md`](selling-kit/01-platform-comparison.md) | Etsy vs Redbubble: fees, traffic, the verdict |
| [`02-pricing-and-profit.md`](selling-kit/02-pricing-and-profit.md) | Exact price points and profit per product type |
| [`03-listing-copy-templates.md`](selling-kit/03-listing-copy-templates.md) | Copy-paste titles, descriptions, attributes |
| [`04-file-specs-and-upload.md`](selling-kit/04-file-specs-and-upload.md) | Upload specs + step-by-step walkthroughs |
| [`05-keywords-and-tags.md`](selling-kit/05-keywords-and-tags.md) | The 13-tag Etsy / 15-tag Redbubble formulas |
| [`06-launch-plan-30-days.md`](selling-kit/06-launch-plan-30-days.md) | Day-by-day launch, marketing, iteration |
| [`07-legal-ip-tax.md`](selling-kit/07-legal-ip-tax.md) | Copyright, AI disclosure, trademarks, tax |
| [`profit-calculator.py`](selling-kit/profit-calculator.py) | Working calculator for both platforms |

## Quick start

```bash
cd selling-kit
python3 idea-evaluator.py --types                     # which categories work
python3 idea-evaluator.py --template > my-4-ideas.txt  # fill in your ideas
python3 idea-evaluator.py my-4-ideas.txt               # verdict + profit
```

## The headline finding

On Redbubble's default **Standard** tier a $24 t-shirt earns you **$2.00**.
The same design on Etsy via a print-on-demand partner earns roughly **$13–17**.
Etsy is where the profit is; Redbubble is free, hands-off distribution. Do both,
prioritise Etsy.
