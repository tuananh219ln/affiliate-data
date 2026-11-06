# Plan: affiliate videos on Facebook and TikTok

The goal: a team earns Shopee and TikTok Shop affiliate commission by posting short product
videos on Facebook and TikTok, each carrying the product's affiliate link. Everything is built
here, in affiliate-data; it does not feed Reels Studio (that project decided to take Shopee
data only through Shopee's Open API, never by scraping). This file is the shared picture of the
whole workflow; update it when a step changes.

## The workflow

```text
1. Pick products ──> 2. Affiliate links ──> 3. Make the video ──> 4. Post ──> 5. Measure
```

| Step | What happens | Status |
| --- | --- | --- |
| Web pages | Members sign in, run picks, follow jobs, see revenue; admins manage members | Built |
| 1. Pick products | From a list of keywords, the cheapest, best-paid products from trusted shops (`shopee.picks`, `tiktok.picks`, `/picks`) | Built for Shopee and TikTok Shop |
| 2. Affiliate links | Shopee: short link from the custom-link tool, made for each pick. TikTok Shop: the product is added to the creator's showcase in the app (no web tool) | Shopee built; TikTok by hand |
| 3. Make the video | From a picked product: a script and caption, then its photos cut into a 9:16 video with FFmpeg | To do |
| 4. Post | Facebook Page: video with the link in the caption or first comment, through the Graph API. TikTok: video and caption ready to post by hand (product tagged in the app), or the Content Posting API once approved | To do |
| 5. Measure | Orders and commission per day; per video once each video has its own link (Sub IDs) | Daily built; per video to do |

Trend research feeds step 1: `tiktok.trending` shows which keywords' videos get views.

## Next steps, in order

1. **Check the affiliate pages against real accounts.** Run `shopee.picks` and `tiktok.picks`
   once each with `"dump": true`; fix the offer, shop-badge and short-link keys from the dumps
   (with tests). Picks are only as good as what the parsers read.
2. **Make the video (step 3).** Product photos from the pick, a short script and caption
   written by an LLM, voice-over optional, rendered to 9:16 MP4 by FFmpeg in the worker (a new
   job kind, one at a time like the rest). A page to review and download each video.
3. **Facebook posting (step 4).** Members connect their Pages (Graph API token, stored
   encrypted like the platform sessions); a video is posted to a Page as a Reel with its link.
   Needs a Meta app with the pages permissions.
4. **Per-video links (step 5).** Shopee custom links take Sub IDs: one link per video and Page,
   so the report says which video sold. Needs the custom-link page's Sub ID field (from step 1's
   dumps).
5. **TikTok posting.** First: a download of the video with its caption for posting by hand.
   Later the Content Posting API, if TikTok approves the app.
6. **Per-member data.** Platform logins, Pages and revenue owned by the member who added them,
   once more than one person runs their own accounts.

## Rules that hold everywhere

- Data collection stays slow and logged-in by a person; on a captcha or login wall the job stops
  (see [AGENTS.md](../AGENTS.md)). No captcha solving, hidden automation or rotating accounts.
- Posting uses the platforms' official APIs or a person, never browser automation of the posting
  pages.
- Affiliate videos say they are paid promotion, as each platform's branded-content rules ask;
  check each platform's current rules on links in captions (TikTok limits them).
- Move to the official Shopee Affiliate Open API and TikTok Shop Affiliate API as soon as the
  accounts are approved; they replace the scraping in steps 1, 2 and 5.
