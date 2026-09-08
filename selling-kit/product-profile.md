# Product Profile — the source of truth

Fill this in (or send me the artwork and I'll fill it in). Everything else in
this kit — titles, descriptions, tags, prices — is generated from this page.

---

## 1. The product

| Field | Your answer |
|---|---|
| Working name | `{{PRODUCT_NAME}}` |
| What is it, literally? | `{{e.g. "a line-art illustration of a heron standing in reeds"}}` |
| Style / aesthetic | `{{e.g. minimal line art, retro 70s, watercolour, kawaii, vintage botanical}}` |
| Dominant colours | `{{list 3-6}}` |
| Any text in the artwork? | `{{exact wording, or "none"}}` |
| Original dimensions | `{{px x px}}` |
| File format(s) you have | `{{PNG / JPG / SVG / PDF / AI / PSD}}` |
| Background | `{{transparent / white / coloured}}` |
| Who made it? | `{{you drew it / you generated it with AI / you licensed it / hybrid}}` |
| If AI: which tool + which paid plan? | `{{tool, plan — this determines your commercial licence}}` |

## 2. Rights check (do not skip)

Tick every one. If you cannot tick one, **do not list it** — see
`07-legal-ip-tax.md`.

- [ ] I created this myself, or I hold a commercial licence for every element.
- [ ] It contains **no** trademarked characters, logos, brands, or celebrity likenesses.
- [ ] It contains **no** song lyrics, movie quotes, or brand slogans.
- [ ] Any font used is licensed for commercial use (check the foundry's EULA).
- [ ] If AI-generated: my tool's plan grants **commercial** usage rights.
- [ ] I've run the main keywords through a trademark search (USPTO / EUIPO / IP India).
- [ ] I have made substantial human edits (matters for copyright *and* for
      Etsy's Creativity Standards).

## 3. Which niches does it fit?

Buyers search by **subject + style + recipient + occasion**, not by "art".
Pick 2–3 that genuinely apply — this drives all your tags.

| Angle | Your answer |
|---|---|
| Subject | `{{e.g. heron, bird, nature, wildlife}}` |
| Style niche | `{{e.g. minimalist, boho, cottagecore, mid-century}}` |
| Who buys it / gift recipient | `{{e.g. birdwatchers, new homeowners, anglers}}` |
| Occasion | `{{e.g. housewarming, birthday, Christmas}}` |
| Room / placement | `{{e.g. bathroom, nursery, office, cabin}}` |
| Seasonal hook | `{{e.g. spring, none}}` |

## 4. Product types to enable

Tick what you'll actually sell. Prices for each are in
`02-pricing-and-profit.md`.

**Redbubble** (upload once, auto-applies to 70+ products):
- [ ] Die-cut stickers (small / medium / large)
- [ ] Essential T-shirt
- [ ] Classic / Premium T-shirt
- [ ] Hoodie / sweatshirt
- [ ] Mug (11oz / 15oz)
- [ ] Art print / poster / metal print
- [ ] Phone case
- [ ] Tote bag
- [ ] Notebook / journal
- [ ] Throw pillow / blanket
- [ ] Mouse pad

**Etsy** (pick ONE model):
- [ ] **Digital download** — buyer prints it themselves. Zero COGS, ~83% margin.
- [ ] **POD physical** — Printify/Printful/Gelato prints & ships. ~30–50% margin.
- [ ] **Handmade / self-shipped** — you make and post it yourself.

## 5. Your cost inputs

| Field | Your answer |
|---|---|
| Seller country | `{{US / UK / EU / IN / MY / ...}}` — sets your payment processing fee |
| Etsy: POD production cost per unit | `{{e.g. $11.50 for a Bella+Canvas 3001 tee}}` |
| Etsy: shipping you'll charge | `{{$X or "free"}}` |
| Etsy: your time per order (packing, CS) | `{{minutes}}` |
| Redbubble: your account tier | `{{Standard — new accounts always start here}}` |
| Monthly ad budget, if any | `{{$X}}` |

## 6. Targets

| Field | Your answer |
|---|---|
| Minimum acceptable profit per sale | `{{$X}}` |
| Sales/month goal (month 3) | `{{X}}` |
| Monthly income goal | `{{$X}}` |

---

## Then run the numbers

```bash
python3 profit-calculator.py etsy --price {{X}} --shipping {{X}} --cogs {{X}} --country {{us}}
python3 profit-calculator.py redbubble --base {{X}} --markup 20 --tier standard
python3 profit-calculator.py etsy --price 20 --cogs {{X}} --solve --target-profit {{X}}
```

Paste the output into section 7 below so your final prices are recorded in one
place.

## 7. Final price decisions

| Platform | Product | Retail price | Your profit/sale | Decision |
|---|---|---|---|---|
| Etsy | `{{digital download}}` | `{{}}` | `{{}}` | `{{}}` |
| Etsy | `{{t-shirt via POD}}` | `{{}}` | `{{}}` | `{{}}` |
| Redbubble | sticker | `{{}}` | `{{}}` | `{{}}` |
| Redbubble | essential t-shirt | `{{}}` | `{{}}` | `{{}}` |
| Redbubble | art print | `{{}}` | `{{}}` | `{{}}` |
