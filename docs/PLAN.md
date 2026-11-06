# Plan: affiliate videos on Facebook and TikTok

The goal: earn Shopee and TikTok Shop affiliate commission by posting short product videos on
Facebook and TikTok, each carrying the product's affiliate link. This file is the shared
picture of the whole workflow and of which part lives where; update it when a step changes.

## The workflow

```text
1. Pick products ──> 2. Affiliate links ──> 3. Make the video ──> 4. Post ──> 5. Measure
   affiliate-data      affiliate-data          Reels Studio         FB / TikTok   affiliate-data
```

| Step | What happens | Where | Status |
| --- | --- | --- | --- |
| 1. Pick products | From a list of keywords, the cheapest, best-paid products from trusted shops (`shopee.picks`, `tiktok.picks`, `GET /api/products/picks`) | affiliate-data | Built for Shopee and TikTok Shop |
| 2. Affiliate links | Shopee: short link from the custom-link tool, made for each pick. TikTok Shop: the product is added to the creator's showcase in the app (no web tool) | affiliate-data / by hand | Shopee: built. TikTok: by hand |
| 3. Make the video | Reels Studio imports the picks (name, price, images, link) and builds the video | Reels Studio | To do: "Import from Affiliate Data" |
| 4. Post | Facebook Page: video with the link in the caption or first comment. TikTok: video with the product tagged (TikTok Shop) | Posting tool (official APIs) | To decide |
| 5. Measure | Orders and commission per day; later per video (see Sub IDs) | affiliate-data (`*.report`, `/api/conversions/summary`) | Reports built; per-video to do |

Trend research feeds step 1: `tiktok.trending` shows which keywords' videos get views.

## Next steps, in order

1. **Check the affiliate pages against real accounts.** Run `shopee.picks` and `tiktok.picks`
   once each with `"dump": true`; fix the offer, shop-badge and short-link keys from the dumps
   (with tests).
   Nothing past this is worth building until picks come back with prices, commission and links.
2. **Reels Studio import.** A button on its Affiliate page that calls `GET /api/products/picks`
   and fills the product list.
3. **Per-video tracking with Sub IDs.** Shopee custom links take Sub IDs; one link per video and
   channel would let the report say which video sold. Needs the custom-link page's Sub ID field.
4. **Posting.** Decide the tool: post by hand from Reels Studio's output, or through the
   official Facebook Graph API (Page videos/Reels) and TikTok Content Posting API, which need app
   review. Check each platform's current rules for links: TikTok limits links in captions, so
   Shopee links on TikTok usually go in the bio; TikTok Shop products are tagged in the app.

## Rules that hold everywhere

- Data collection stays slow and logged-in by a person; on a captcha or login wall the job stops
  (see [AGENTS.md](../AGENTS.md)). No captcha solving, hidden automation or rotating accounts.
- Posting uses the platforms' official APIs or a person, never browser automation of the posting
  pages.
- Affiliate videos say they are paid promotion, as each platform's branded-content rules ask.
- Move to the official Shopee Affiliate Open API and TikTok Shop Affiliate API as soon as the
  accounts are approved; they replace steps 1, 2 and 5 here.
