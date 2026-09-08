# 04 — File specs and upload walkthrough

Get this wrong and your product arrives blurry, or your upload is rejected.
Specs verified May–July 2026.

---

## ⚠️ First: your source file is a PDF

You sent `hhgg4.pdf`. **A PDF is almost never the right file to sell from.**
Both platforms want raster images (PNG/JPG), and Etsy's digital-download buyers
want print-ready JPG or PDF-per-size.

What to do depends on what's *inside* the PDF:

| If the PDF contains… | Then… |
|---|---|
| Vector artwork (from Illustrator, Affinity, Inkscape, Canva) | **Excellent.** Open it in the vector app and export PNG at 4500×5400 px or larger. You can scale infinitely with zero quality loss. |
| A high-res raster image (3000px+) | Fine. Extract it: `pdfimages -all hhgg4.pdf out` or open in Photoshop/GIMP and export. |
| A low-res raster image (<1500px) | Problem. Upscaling won't add real detail. Either redraw it, or limit yourself to small products (stickers, mugs, phone cases) and skip wall prints. |
| A design doc / brief / invoice | Then I don't have your artwork at all — please send the actual design. |

**Inspect it before anything else:**

```bash
# poppler-utils — install if missing:
#   Debian/Ubuntu: sudo apt install poppler-utils
#   macOS:         brew install poppler
#   Windows:       download poppler for Windows and add to PATH
pdfinfo hhgg4.pdf                    # page size, page count, producer app
pdfimages -list hhgg4.pdf            # resolution of EVERY embedded image
```

`pdfimages -list` is the important one: it prints the real pixel dimensions of
each image inside the PDF. The page size (`pdfinfo`) tells you nothing — a PDF
page can be "A4" while containing a 400px thumbnail.

If poppler isn't available, **ImageMagick** works and is preinstalled on many
systems:

```bash
identify -verbose hhgg4.pdf | grep -E "Geometry|Resolution|Colorspace"
convert hhgg4.pdf[0] -density 300 extracted.png    # rasterise page 1 at 300 DPI
identify extracted.png                             # check what you actually got
```

**Read the numbers:** if the embedded images are under ~2,000 px wide, that's
your hard ceiling on product size — no software can add detail that isn't there.
Also note the *producer* field from `pdfinfo`: it tells you what app made the
PDF (Illustrator/Canva/InDesign = likely vector and excellent; a phone scanner or
screenshot = raster and limited).


---

## The master-file rule

Build **one** master file, then export down from it for every platform and
product. Never upscale — upscaling invents pixels.

```
MASTER:  5000 × 5500 px, 300 DPI, RGB/sRGB, transparent background, PNG
             │
             ├──→ Redbubble   : upload master directly (caps at 13500 × 13500)
             ├──→ Etsy POD    : 4500 × 5400 px PNG (Printify/Printful)
             ├──→ Etsy photos : 2000 × 2500 px JPG @ 80% quality (<1 MB each)
             └──→ Etsy digital: 5 ratio-pack ZIPs, JPG at 300 DPI, each <20 MB
```

5000×5500 at 300 DPI covers every platform's apparel requirement. Redbubble's
published ideal for full-bleed products is **7632 × 6480 px** — go there if your
art will cover duvet covers or 24×36" prints.

---

## Redbubble specs

| Requirement | Value |
|---|---|
| Accepted formats | **PNG, JPEG**, static GIF. **No SVG, no PDF.** |
| Maximum dimensions | 13,500 × 13,500 px (absolute); 9,075 × 6,201 px standard ceiling |
| Practical floor | 1,024 px on the shortest side — but this triggers quality warnings |
| Recommended DPI | 300 |
| Max file size | ~300 MB |
| Colour mode | **RGB / sRGB** (not CMYK — Redbubble converts) |
| Background | **Transparent PNG** for stickers, apparel, cases |

**Per-product recommended sizes:**

| Product | Recommended px |
|---|---|
| T-shirts / hoodies | 2,875 × 3,900 (min) → 4,500 × 5,400 (safe) |
| Stickers | 2,800 × 2,800 |
| Art prints / posters | 3,840 × 3,840 |
| Phone cases | 1,600 × 3,200 |
| Mugs | 2,400 × 1,000 |
| Full-bleed (duvet, blanket) | 7,632 × 6,480 |

Redbubble's uploader shows a **quality indicator**. Green = fine. Amber/red =
your file is under threshold and will print soft on large products. Fix it
before publishing; you can't fix a bad print after a customer receives it.

---

## Etsy specs

### Listing photos (what buyers see in search)

| Spec | Value |
|---|---|
| Recommended | **2,000 × 2,500 px (4:5)** or 2,000 × 2,000 (1:1) |
| Minimum | 500 px wide (but it'll look terrible next to competitors) |
| Max dimensions | ~3,000 × 3,000 px |
| Formats | JPG, PNG, GIF. **No WebP, no TIFF, no BMP, no SVG.** |
| Max photos per listing | **10** — use all 10 |
| Search thumbnail | Auto-cropped to 570 × 570 from photo #1 |

Export photos as **JPEG at 80% quality**, targeting 500–900 KB. That's visually
indistinguishable from 100% and avoids upload failures.

### Digital download files (what the buyer actually receives)

| Spec | Value |
|---|---|
| Max files per listing | **5** |
| Max size per file | **20 MB each** |
| Accepted types | JPG, PNG, PDF, ZIP |
| Resolution | **300 DPI at full print size** |

**The 5-file problem and the ZIP solution.** Buyers need many print sizes; you
only get 5 slots. Group sizes by **aspect ratio** into ZIPs:

| ZIP | Ratio | Sizes inside |
|---|---|---|
| `01-ratio-2x3.zip` | 2:3 | 4×6, 6×9, 8×12, 10×15, 12×18, 16×24, 20×30 in |
| `02-ratio-3x4.zip` | 3:4 | 6×8, 9×12, 12×16, 15×20, 18×24 in |
| `03-ratio-4x5.zip` | 4:5 | 8×10, 12×15, 16×20, 20×25, 24×30 in |
| `04-ratio-ISO.zip` | A-series | A5, A4, A3, A2, A1 |
| `05-extras.zip` | misc | 5×7, 8.5×11, 11×14, 11×17, 13×19, 20×24 in |

**Pixel dimensions at 300 DPI:**

| Print size | Pixels |
|---|---|
| 5 × 7 in | 1500 × 2100 |
| 8 × 10 in | 2400 × 3000 |
| 11 × 14 in | 3300 × 4200 |
| 16 × 20 in | 4800 × 6000 |
| 18 × 24 in | 5400 × 7200 |
| 24 × 36 in | 7200 × 10800 |
| A4 | 2480 × 3508 |
| A3 | 3508 × 4961 |

⚠️ A 24×36" PNG at 300 DPI can be **50–80 MB** — way over Etsy's 20 MB cap.
Save digital-download artwork as **JPG at 300 DPI** (typically 5–12 MB for that
size). PNG only when transparency is genuinely required. Verify each ZIP:

```bash
du -h *.zip          # every one must be under 20 MB
```

### Other Etsy image assets

| Asset | Size |
|---|---|
| Shop banner (big) | 3,360 × 840 px |
| Mini banner | 1,200 × 300 px |
| Shop icon | 500 × 500 px |

---

## Pre-flight checklist (run this on every file)

```bash
# What is it, really?
identify -verbose artwork.png | grep -E "Geometry|Resolution|Colorspace|Type"
#   Geometry    -> pixel dimensions
#   Resolution  -> DPI metadata
#   Colorspace  -> must be sRGB, NOT CMYK
#   Type        -> "TrueColorAlpha" means transparency is present

# File size
du -h artwork.png

# Transparency check
identify -format "%A\n" artwork.png      # True = has alpha channel
```

Before uploading, tick every box:

- [ ] 300 DPI at the intended print size (not just DPI metadata on a small image)
- [ ] **RGB / sRGB**, never CMYK
- [ ] Transparent background where the product needs one (stickers, apparel, cases)
- [ ] No white box or halo around the artwork (the #1 amateur giveaway)
- [ ] Master is ≥ 4,500 × 5,400 px
- [ ] Nothing important within the outer 5% (bleed/trim safety margin)
- [ ] Text is legible at sticker size (~3 inches wide)
- [ ] Colours checked against a printed sample, not just your screen
- [ ] JPG at ≤20 MB for Etsy digital; ≤1 MB at 80% quality for Etsy photos
- [ ] No watermark, no mockup frame, no border burned into the art

---

## Upload walkthrough — Redbubble

1. Sign in → **Add New Work**.
2. Upload the master PNG. Wait for the quality indicator — it must be green.
3. **Title** (≤50 chars) and **Description** (~500 chars) — see `03`.
4. **Tags**: up to 15, comma-separated, strongest first. No trademarks.
5. **AI disclosure**: tick the checkbox/dropdown if AI was involved. This becomes
   publicly visible under "Creation Info". New accounts are limited to **5
   AI-tagged uploads per day** (20/day once you have 100+ sales).
6. **Enable and position each product.** Do not accept defaults. Resize,
   reposition, check dark vs light garment colours.
7. **Set markup**: 20% everywhere; 50–100% on stickers.
8. Preview every enabled product. Disable anything that looks wrong.
9. **Save as a collection** — helps discovery and speeds up future uploads.
10. Publish. Then buy one sample sticker and one sample shirt before promoting.

## Upload walkthrough — Etsy

**Digital download:**
1. Shop Manager → **Listings → Add a listing**.
2. Choose type: **Digital**. (This removes shipping and enables instant delivery.)
3. Upload your 5 ZIPs (each <20 MB).
4. Title (140 chars), 13 tags, category `Digital Prints`.
5. Attributes: **"Designed by a seller"** if AI-assisted. Fill every dropdown.
6. Upload 10 photos (mockups, size grid, how-it-works).
7. Description — paste the template from `03`, including the AI disclosure line.
8. Price. Run it through the calculator first.
9. Set quantity to **999** so the listing auto-renews.
10. Publish. Buyers get files automatically the moment payment clears.

**Physical via POD:**
1. Connect Printify/Printful/Gelato to Etsy (Settings → Production partners).
2. Create the product in the POD app, attach your artwork, pick the blank.
3. Publish **to** Etsy from the POD app — it syncs variants and pricing.
4. Back in Etsy: fix the title, tags and description (POD apps generate weak copy).
5. Replace the POD mockups with better ones — this is the single highest-impact
   change you can make.
6. **Declare the production partner** in listing attributes with your role and
   their location. Required, and non-disclosure is a suspension risk.
7. Set processing time to match your partner's real production + transit.
8. Order a sample. Always.

---

## Common failures and fixes

| Symptom | Cause | Fix |
|---|---|---|
| "Design quality is low" warning | File under Redbubble's threshold | Re-export at ≥3,600 × 4,800 px |
| Blurry on large prints, fine on stickers | Master too small | Rebuild from vector, or drop the large products |
| White box around art on dark shirts | No transparency | Export PNG with alpha; check `identify -format "%A"` |
| Etsy photo upload stalls | File >1 MB, or WebP/TIFF | Re-export JPG at 80%, 2,000 px long side |
| Etsy rejects download file | >20 MB | JPG instead of PNG; or split the ZIP |
| Colours print dull/wrong | CMYK source, or uncalibrated screen | Convert to sRGB; order a physical sample |
| Art cut off on phone case | Camera cutout | Reposition; keep focal point centred-low |
| Duvet looks broken | Small art on a full-bleed product | Use a seamless pattern, or disable the product |
