---
name: kindle-reads
description: Find a few fresh, genuinely good articles (by default two from Hacker News and two from X with Grok's help), package the complete originals and their images into one clean EPUB, and email it to the user's Kindle. Use whenever the user asks for articles, reads or a digest for their Kindle or e-reader, wants something good to read sent to them, or asks for web articles turned into an EPUB, even if they never say "EPUB".
---

# Kindle reads

The user wants to open their Kindle and find a few articles worth their time, exactly as the authors wrote them. Two things spoil that: a weak or stale pick, and anything standing between the reader and the article (summaries, notes, missing images). The steps below guard against both.

## 1. Settle the brief

Take these from the request, then from memory; ask only for what is still missing:

- how many articles and from where (default: two from Hacker News, two from X)
- topics and tone
- freshness window (default: originally published in the last 24 hours)
- the Kindle address and the sender account. They are the user's own details: never write them into this skill or any shared file.

Honour named exceptions and past complaints ("that one read like an ad", "too old").

## 2. Find candidates

Cast wide, then read. Titles and scores are weak signals; good personal posts often sit at two or three points.

**Hacker News.** Pull every story in the window, not just the front page:

```bash
curl -s --get "https://hn.algolia.com/api/v1/search_by_date" --data-urlencode "tags=story" \
  --data-urlencode "numericFilters=created_at_i>$(( $(date +%s) - 26*3600 )),points>1" \
  --data-urlencode "hitsPerPage=1000"
```

**X.** In the user's signed-in browser, ask Grok for long-form reads on the topics that were first published inside the window, with the article URL, the sharing post and how it checked the date. Ask for a second pass (native X Articles; essays people shared that day). Also search X directly, for example `url:x.com/i/article <topic terms> since:<date> min_faves:50`. Open each sharing post yourself. Read the community note if there is one; viral "an agent did this for me" stories are often invented.

## 3. Choose

Read every finalist in full before picking it.

- **Fresh.** Check the date on the article itself (`article:published_time`, a `<time>` element, the visible date). A submission or repost date proves nothing.
- **Worth reading.** Prefer independent first-person stories, experiments, creative uses and practical experience. Skip vendor pitches, launch posts, promotional tutorials, pieces that end in a funnel, and dense papers unless asked for.
- **Complete.** If an article is paywalled or cannot be captured whole, pick another.

If fewer articles qualify than were asked for, say so before sending. Never pad with weaker or older pieces, and never substitute a summary.

## 4. Capture each article

Work in a scratch folder. For each article save one HTML fragment holding only the article body, plus its images.

- Blogs: `curl` the page and cut out the article element. Drop navigation, share buttons, subscribe boxes, comments and related posts. Change no words.
- X Articles: read the DOM in the signed-in browser and rebuild headings, lists, emphasis and links from it.
- Images: download every one. Convert to JPEG at most 1400 px wide and point each `<img src>` at the local file:
  `ffmpeg -i in.webp -vf "scale='min(1400,iw)':-2" -q:v 3 out.jpg` (flatten transparent PNGs onto white; `sips -s format jpeg` handles animated WebP).
- Captions belong with their image: `<figure><img/><figcaption>…</figcaption></figure>`.
- Video and other embeds cannot go in an EPUB. Replace each with a still (thumbnail, or `ffmpeg -ss 10 -i v.mp4 -frames:v 1 still.jpg`) linked to the video, with a caption such as `Video: <title>`. Tell the user afterwards.

## 5. Build

Write `book.json` (format in the header of `scripts/build_epub.py`) and run:

```bash
python3 scripts/build_epub.py book.json out/<title>.epub
```

The script produces a contents page and one chapter per article: title, the original subtitle if any, author and date, the article, then a one-line source and rights note. It adds nothing else, and neither should you: no introduction, commentary, takeaways or reasons for the choice. It stops on anything it cannot carry faithfully, so fix the fragment rather than working around the error.

## 6. Check before sending

- Compare the word counts the script prints with the originals.
- Unzip the EPUB and look at every chapter, for example with headless Chrome at reader width:
  `chrome --headless=new --window-size=600,5000 --screenshot=ch.png file:///…/chapter-01.xhtml`
  Look for missing images, stray site chrome, broken lists and captions that have drifted from their image.

## 7. Send and report

Email the EPUB as an attachment to the Kindle address from the sender account (it must be on the user's approved senders list). Use the book title as the subject, leave the body empty, and confirm the mail client reports it sent. Some browser tools only attach files from inside the working folders, so write the EPUB there.

Then report briefly: the articles with links and publication dates, good candidates left out and why, anything that could not be included as published (videos), and what you did not verify (usually arrival on the device).
