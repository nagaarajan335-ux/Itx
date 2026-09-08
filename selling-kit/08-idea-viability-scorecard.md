# 08 — Idea viability scorecard: does it work, and if not why?

Use `idea-evaluator.py` to apply this framework automatically.

```bash
cd selling-kit
python3 idea-evaluator.py --types                    # see the category table
python3 idea-evaluator.py --template > my-4-ideas.txt # get a spec to edit
python3 idea-evaluator.py my-4-ideas.txt              # evaluate all 4
python3 idea-evaluator.py --quick "my idea name" --type niche-hobby --resolution 4500
```

---

## The five reasons an idea DOES NOT WORK

These are **hard fails**. The evaluator prints `[X] DOES NOT WORK` and refuses
to recommend a launch until they're fixed. In order of how often they kill shops:

### 1. It infringes someone's IP

**Symptom:** the design contains a character, brand logo, celebrity likeness,
sports team, song lyric, movie quote, or franchise word — in the artwork *or* in
your title/tags.

**Why it fails:** Both platforms run automated IP scanners. A hit means the
design is removed **and** a strike is recorded against your account. Enough
strikes = permanent suspension, with any accumulated earnings frozen. This is
the single most common cause of print-on-demand account death, and fan art is
the most common trigger.

It is not a "risk you can manage". Fan art sits up for months and then gets
swept in a batch takedown — *after* you've built income on it.

**Fix:** remove every protected element, or abandon the idea. Trademark-search
your phrases first (USPTO classes 16, 25, 35). See `07-legal-ip-tax.md`.

### 2. The artwork is too low-resolution to print

**Symptom:** master file under 1,500px.

**Why it fails:** You cannot add detail that isn't there. Upscaling invents
soft, muddy pixels. At 1,024px even a sticker prints poorly, and apparel or
wall art is impossible — Redbubble will show a quality warning on upload.

This is the **specific risk with AI-generated art**, which typically outputs
1024–2048px. Fine for stickers; unusable for a 24×36" print.

| Resolution | What you can safely sell |
|---|---|
| 6,000px+ | Everything, including 24×36" wall art and full-bleed duvets |
| 3,600–6,000px | Everything except the largest full-bleed products |
| 1,500–3,600px | Stickers, mugs, phone cases, small prints only |
| Under 1,500px | **Nothing reliably. Hard fail.** |

**Fix:** rebuild from the original vector, re-render at 5,000×5,500px, or use a
real upscaler (Topaz Gigapixel, Real-ESRGAN) and then repaint/redraw the key
areas. See `04-file-specs-and-upload.md`.

### 3. You're pricing a physical item under $4 on Etsy

**Symptom:** a sticker, keyring or similar at $2.99.

**Why it fails:** Etsy's flat fees dominate cheap listings.

| Price | Etsy fees | Effective rate |
|---|---|---|
| $2.99 | $0.73 | **24.6%** |
| $4.99 | $0.92 | 18.5% |
| $9.99 | $1.40 | 14.0% |

At $2.99 you surrender a quarter of the sale **before** paying for the vinyl,
the envelope and the postage. You lose money on every order, and selling more
makes it worse.

**Fix:** bundle five at $9.99, or raise the price. Never match a competitor who
is pricing below cost.

### 4. It isn't your own work

**Symptom:** a downloaded design, an "AI art pack" you bought, or a competitor's
listing re-uploaded.

**Why it fails:** violates both platforms' terms regardless of how the art was
made. Redbubble's rules turn on "yours vs not yours", not "human vs AI". Also
leaves you with no copyright standing if someone steals it back.

**Fix:** create original work.

### 5. Stickers-only with no other product

**Symptom:** the idea only exists as a $2 sticker.

**Why it fails:** the maths don't reach the payout threshold.

| Redbubble sticker markup | Net per sticker | Sales needed to reach the $20 payout |
|---|---|---|
| 20% | $0.20 | **101** |
| 50% | $0.35 | **57** |
| 100% | $0.60 | **34** |

Under $20 your earnings roll over and you simply don't get paid that month.

**Fix:** keep stickers — they're an excellent traffic and review builder — but
add t-shirts, mugs, or especially **digital downloads** where the margin is real.

---

## The six things that quietly cost you money (fixable warnings)

These don't kill the idea, but the evaluator flags them because they're the
difference between a shop that earns and one that stalls.

| # | Warning | Fix |
|---|---|---|
| 1 | **Saturated niche** (>200k Etsy results) | Attack a long-tail angle: profession, hobby, room, colourway, region. You can't out-rank a 40,000-review shop on "wall art". |
| 2 | **No digital download version** | Digital is 85% margin, $0 COGS, instant delivery, no returns, no shipping, no inventory. Same artwork. Always list it. |
| 3 | **Borderline resolution** (1,500–3,600px) | Limit product types to small items, or rebuild the master. |
| 4 | **Seasonal idea listed late** | List 6–8 weeks early. Etsy needs 2–4 weeks just to index a new listing. |
| 5 | **AI-assisted without disclosure plan** | Etsy: "Designed by a seller" + disclosure sentence. Redbubble: tick the AI box. Make substantial human edits — it's required, and it gives you copyright standing. |
| 6 | **Seamless pattern not on full-bleed products** | Patterns are the only art that works on duvets and blankets — the highest-ticket Redbubble items. Enable them. |

---

## The scoring model

| Dimension | Weight | What drives it |
|---|---|---|
| **Demand** | /10 | Search volume for the category |
| **Competition** (10 = easy) | /10 | Inverse of results count in your niche |
| **Margin** | /10 | Average profit margin across your chosen products |
| **Scalability** | /10 | How many product types one design supports, and how easily it makes variants |
| **IP safety** | /10 | Inverse of infringement risk |
| **OVERALL** | /10 | Mean of the five |

| Overall | Verdict |
|---|---|
| Any hard fail | `[X] DOES NOT WORK` — fix before launching |
| ≥ 7.0, no warnings | `[OK] WORKS` |
| ≥ 5.5 | `[~] WORKS WITH FIXES` |
| < 5.5 | `[!] WEAK — REWORK IT` |

Note: the Redbubble Standard-tier 50% fee is **deliberately not scored** — it's
a universal platform fact, not a defect of your idea. It's reported separately
as a standing reality check.

---

## Category reference

Run `python3 idea-evaluator.py --types` for the live table. Summary:

| Category | Demand | Competition | IP risk | Best platform | Verdict for a new shop |
|---|---|---|---|---|---|
| **Niche hobby / profession** | 6 | **3** | 2 | Etsy | ⭐ **Best starting point.** Low competition, high buyer intent, winnable long-tail keywords. |
| **Personalised / custom** | 8 | 5 | 1 | Etsy | ⭐ Highest-converting Etsy category. Costs you per-order labour but commands a premium. |
| Botanical / vintage | 7 | 5 | 2 | Etsy | Strong and evergreen. Easy variants. |
| Minimalist line art | 7 | 6 | 1 | Etsy | Good. Very easy to make colourway variants. |
| Original illustration | 6 | 6 | 3 | Both | Fine. Stickers build the audience for the rest. |
| Seasonal | 9 | 9 | 4 | Both | Huge spikes then zero. Only worth it if you list early. |
| Funny text / meme | 8 | 8 | **6** | Redbubble | Impulse buys work well, but the **IP trap is severe** — quotes and slogans are frequently trademarked. |
| Photography | 5 | 7 | 1 | Etsy | Weak on apparel/stickers. Needs very high resolution. |
| Seamless pattern | 5 | **4** | 1 | Redbubble | The only category that works on full-bleed home decor. Underexploited. |
| Abstract / geometric | 4 | 8 | 1 | Etsy | ⚠️ Hardest to differentiate. Needs a named colour/trend angle. |

---

## What a good idea looks like — worked example

```
Birdwatcher heron field-guide art
  type: niche-hobby
  resolution: 6000px
  ip_risk: none
  competition: low
  products: digital, digital-bundle, sticker, tshirt, artprint, mug
```

| Product | Etsy price | Etsy profit | Redbubble retail | RB profit |
|---|---|---|---|---|
| Digital bundle | $19.99 | **$17.64** | n/a | — |
| Digital download | $7.99 | **$6.78** | n/a | — |
| Art print | $28.99 | **$18.31** | $22.80 | $1.90 |
| T-shirt | $24.99 | **$13.19** | $24.00 | $2.00 |
| Mug | $19.99 | **$12.67** | $15.60 | $1.30 |
| Sticker | $4.99 | **$2.47** | $2.98 | $0.35 |

**Score: 8.1/10 → `[OK] WORKS`.**

Why it works: low competition (a new shop can actually rank), zero IP risk,
6,000px master supports every product type, six revenue streams from one design,
and it includes the two highest-margin products (digital + art print).

Best single product: **art print at $28.99 → $18.31 profit.**

| Sales/month | Etsy | Redbubble | Combined |
|---|---|---|---|
| 10 | $183 | $19 | **$202** |
| 25 | $458 | $48 | **$506** |
| 50 | $916 | $95 | **$1,011** |

---

## The multiplier most people miss

One good idea is worth far more than one listing. Take that heron design:

```
1 design
  × 5 colourways (sage, terracotta, navy, black, cream)
  × 3 formats (single print, set of 3, set of 6 bundle)
  × 2 angles (birdwatcher gift / nursery wall art)
  = 30 listings from ONE piece of artwork
```

Thirty listings means thirty times the search surface, thirty times the
impressions, and thirty chances to rank. **Volume of listings is the strongest
predictor of income on both platforms** — far stronger than the quality of any
single design.

So when you evaluate your 4 ideas, the question isn't just "does this work?"
It's "how many listings can I honestly extract from this?"
