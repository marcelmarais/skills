#!/usr/bin/env python3
"""Build a clean EPUB of full articles from a JSON manifest.

Usage: build_epub.py book.json out.epub

book.json (paths are relative to the manifest's folder):

    {
      "title": "Four Reads: 9 November 2026",
      "date": "2026-11-09",
      "language": "en",
      "cover": "img/cover.jpg",
      "chapters": [
        {
          "title": "Article title",
          "subtitle": "Only if the original has one",
          "author": "Author Name",
          "date": "9 November 2026",
          "body": "chapters/article.html",
          "source": "Originally published at example.com, 9 November 2026",
          "url": "https://example.com/article",
          "rights": "© Author Name"
        }
      ]
    }

Each body file is the article's own HTML with site chrome removed. The script
keeps headings, paragraphs, lists, quotes, code, tables, links, figures and
captions, and drops everything else. Headings are shifted so the article's top
level becomes h2 (the chapter title is the h1). Every <img src> must point at a
local JPEG, PNG or GIF. The build stops on anything it cannot carry faithfully
(remote or missing images, video, audio, iframes) so nothing is lost silently.
Standard library only.
"""
import datetime
import html
import json
import os
import re
import sys
import uuid
import zipfile
from html.parser import HTMLParser
from xml.dom import minidom

KEEP = {
    "p", "h2", "h3", "h4", "ul", "ol", "li", "blockquote", "pre", "code", "em", "strong", "i", "b",
    "s", "del", "sub", "sup", "a", "img", "figure", "figcaption", "hr", "br",
    "table", "thead", "tbody", "tr", "th", "td",
}
VOID = {"img", "hr", "br"}
DROP_WITH_CONTENT = {"script", "style", "form", "button", "svg", "noscript", "select", "textarea", "nav"}
UNSUPPORTED = {"iframe", "video", "audio", "object", "embed", "canvas"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif"}
BLOCKS = "p|h2|h3|h4|ul|ol|li|blockquote|figure|figcaption|pre|table|thead|tbody|tr|th|td"


def esc(text, quote=False):
    return html.escape(text, quote=quote)


class Fail(Exception):
    pass


class Sanitiser(HTMLParser):
    def __init__(self, base, shift, images):
        super().__init__(convert_charrefs=True)
        self.base, self.shift, self.images = base, shift, images
        self.out, self.stack, self.used = [], [], []
        self.dropping = 0
        self.pre = 0

    def heading(self, tag):
        return "h%d" % min(4, max(2, int(tag[1]) + self.shift))

    def image(self, attrs):
        src = attrs.get("src") or ""
        if re.match(r"^(?:[a-z]+:)?//|^data:", src, re.I):
            raise Fail("image is not local: %s (download it and point src at the file)" % src[:120])
        path = os.path.normpath(os.path.join(self.base, src))
        ext = os.path.splitext(path)[1].lower()
        if ext not in IMAGE_TYPES:
            raise Fail("image must be JPEG, PNG or GIF: %s" % src)
        if not os.path.isfile(path):
            raise Fail("image file not found: %s" % src)
        name = os.path.basename(path)
        if self.images.setdefault(name, path) != path:
            raise Fail("two different images are both named %s" % name)
        self.used.append(name)
        self.out.append('<img src="images/%s" alt="%s"/>' % (name, esc(attrs.get("alt") or "", True)))

    def handle_starttag(self, tag, attrs):
        if tag in UNSUPPORTED and not self.dropping:
            raise Fail("<%s> cannot go in an EPUB: replace it with a still image and a link" % tag)
        if tag in DROP_WITH_CONTENT:
            self.dropping += 1
            return
        if self.dropping:
            return
        attrs = dict(attrs)
        if tag in HEADINGS:
            tag = self.heading(tag)
        if tag not in KEEP:
            return
        if tag == "img":
            return self.image(attrs)
        if tag in VOID:
            self.out.append("<%s/>" % tag)
            return
        extra = ""
        if tag == "a":
            href = attrs.get("href")
            if not href:
                self.stack.append(None)
                return
            extra = ' href="%s"' % esc(href, True)
        elif tag in ("h2", "h3", "h4") and attrs.get("id"):
            extra = ' id="%s"' % esc(attrs["id"], True)
        if tag == "pre":
            self.pre += 1
        self.out.append("<%s%s>" % (tag, extra))
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in DROP_WITH_CONTENT:
            self.dropping -= 1

    def handle_endtag(self, tag):
        if tag in DROP_WITH_CONTENT:
            self.dropping = max(0, self.dropping - 1)
            return
        if self.dropping:
            return
        if tag in HEADINGS:
            tag = self.heading(tag)
        if tag not in KEEP or tag in VOID:
            return
        if tag == "a" and self.stack and self.stack[-1] is None:
            self.stack.pop()
            return
        if tag not in self.stack:
            return
        while self.stack:
            top = self.stack.pop()
            if top is None:
                continue
            if top == "pre":
                self.pre -= 1
            self.out.append("</%s>" % top)
            if top == tag:
                break

    def handle_data(self, data):
        if self.dropping:
            return
        self.out.append(esc(data if self.pre else re.sub(r"\s+", " ", data)))


def sanitise(fragment, base, images):
    levels = [int(n) for n in re.findall(r"<h([1-6])[\s>]", fragment, re.I)]
    parser = Sanitiser(base, 2 - min(levels) if levels else 0, images)
    parser.feed(fragment)
    parser.close()
    while parser.stack:
        top = parser.stack.pop()
        if top:
            parser.out.append("</%s>" % top)
    text = "".join(parser.out)
    text = re.sub(r"\s*<br/>\s*(</(?:p|h[2-4]|li)>)", r"\1", text)
    text = re.sub(r"<p>\s*(<img [^>]*/>)\s*</p>", r"<figure>\1</figure>", text)
    text = re.sub(r"<p>\s*(<figure>.*?</figure>)\s*</p>", r"\1", text, flags=re.S)
    text = re.sub(r"<(p|li|h[2-4])>\s*</\1>", "", text)
    text = re.sub(r"\s+(</(?:%s)>)" % BLOCKS, r"\1", text)
    text = re.sub(r"(<(?:%s)(?: [^>]*)?>)\s+" % BLOCKS, r"\1", text)
    text = re.sub(r"(</(?:p|h[2-4]|ul|ol|li|blockquote|figure|pre|table|tr)>|<hr/>)\s*", r"\1\n", text)
    return text.strip(), parser.used


CSS = """
body { line-height: 1.5; }
h1.title { font-size: 1.6em; line-height: 1.2; margin: 1.5em 0 0.4em; text-align: left; }
h1.contents { font-size: 1.5em; margin: 1.5em 0 0.5em; text-align: left; }
p.subtitle { font-style: italic; margin: 0 0 0.6em; }
p.byline { font-size: 0.9em; margin: 0 0 2em; }
h2 { font-size: 1.25em; line-height: 1.25; margin: 1.8em 0 0.5em; text-align: left; page-break-after: avoid; }
h3 { font-size: 1.08em; line-height: 1.25; margin: 1.5em 0 0.4em; text-align: left; page-break-after: avoid; }
h4 { font-size: 1em; margin: 1.3em 0 0.3em; text-align: left; page-break-after: avoid; }
p { margin: 0 0 0.9em; text-indent: 0; }
ul, ol { margin: 0 0 0.9em 1.4em; padding: 0; }
li { margin: 0 0 0.4em; }
blockquote { margin: 1em 0 1em 0.6em; padding: 0 0 0 0.9em; border-left: 0.15em solid #888; }
blockquote p:last-child { margin-bottom: 0; }
code, pre { font-family: monospace; font-size: 0.9em; }
pre { margin: 1em 0; white-space: pre-wrap; word-wrap: break-word; line-height: 1.35; }
figure { margin: 1.3em 0; padding: 0; text-align: center; page-break-inside: avoid; }
img { max-width: 100%; height: auto; }
figcaption { font-size: 0.85em; font-style: italic; line-height: 1.35; margin-top: 0.4em; text-align: center; }
table { border-collapse: collapse; margin: 1em 0; font-size: 0.9em; }
th, td { border: 1px solid #888; padding: 0.3em 0.5em; text-align: left; vertical-align: top; }
hr { border: 0; border-top: 1px solid #888; margin: 2em 25%; }
hr.end { margin: 2.5em 0 1em; }
p.source { font-size: 0.8em; line-height: 1.4; margin: 0; }
nav ol { list-style: none; margin: 1.5em 0 0; padding: 0; }
nav li { margin: 0 0 1.2em; }
nav .by { display: block; font-size: 0.85em; font-style: italic; }
"""

PAGE = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="%(lang)s" xml:lang="%(lang)s">
<head>
<meta charset="utf-8"/>
<title>%(title)s</title>
<link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
%(body)s
</body>
</html>
"""


def build(manifest_path, out_path):
    base = os.path.dirname(os.path.abspath(manifest_path))
    with open(manifest_path, encoding="utf-8") as fh:
        book = json.load(fh)
    lang = book.get("language", "en")
    images, chapters = {}, []
    for index, ch in enumerate(book["chapters"], 1):
        for key in ("title", "author", "date", "body", "source", "url"):
            if not ch.get(key):
                raise SystemExit("chapter %d: missing \"%s\"" % (index, key))
        with open(os.path.join(base, ch["body"]), encoding="utf-8") as fh:
            fragment = fh.read()
        try:
            content, used = sanitise(fragment, base, images)
        except Fail as exc:
            raise SystemExit("chapter %d (%s): %s" % (index, ch["title"], exc))
        link = re.sub(r"^https?://(www\.)?", "", ch["url"]).rstrip("/")
        parts = ['<section epub:type="chapter">', '<h1 class="title">%s</h1>' % esc(ch["title"])]
        if ch.get("subtitle"):
            parts.append('<p class="subtitle">%s</p>' % esc(ch["subtitle"]))
        parts.append('<p class="byline">%s · %s</p>' % (esc(ch["author"]), esc(ch["date"])))
        parts.append(content)
        parts.append('<hr class="end"/>')
        parts.append('<p class="source">%s: <a href="%s">%s</a>.%s</p>' % (
            esc(ch["source"]), esc(ch["url"], True), esc(link), " " + esc(ch["rights"]) if ch.get("rights") else ""))
        parts.append("</section>")
        chapters.append({
            "file": "chapter-%02d.xhtml" % index, "title": ch["title"], "author": ch["author"],
            "page": PAGE % {"lang": lang, "title": esc(ch["title"]), "body": "\n".join(parts)},
            "words": len(re.sub(r"<[^>]+>", " ", content).split()), "images": len(used),
        })

    cover = None
    if book.get("cover"):
        cover = os.path.normpath(os.path.join(base, book["cover"]))
        if os.path.splitext(cover)[1].lower() not in IMAGE_TYPES or not os.path.isfile(cover):
            raise SystemExit("cover must be an existing JPEG or PNG: %s" % book["cover"])

    toc = "\n".join('<li><a href="%s">%s</a><span class="by">%s</span></li>'
                    % (c["file"], esc(c["title"]), esc(c["author"])) for c in chapters)
    nav = PAGE % {"lang": lang, "title": "Contents", "body": (
        '<nav epub:type="toc" id="toc">\n<h1 class="contents">Contents</h1>\n<ol>\n%s\n</ol>\n</nav>\n'
        '<nav epub:type="landmarks" hidden="hidden">\n<ol>\n'
        '<li><a epub:type="toc" href="nav.xhtml">Contents</a></li>\n'
        '<li><a epub:type="bodymatter" href="%s">Start</a></li>\n</ol>\n</nav>' % (toc, chapters[0]["file"]))}

    book_id = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, book["title"] + "|" + book.get("date", "")))
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    items = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
             '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
             '<item id="css" href="style.css" media-type="text/css"/>']
    if cover:
        items.append('<item id="cover-image" href="images/%s" media-type="%s" properties="cover-image"/>'
                     % (os.path.basename(cover), IMAGE_TYPES[os.path.splitext(cover)[1].lower()]))
    items += ['<item id="ch%d" href="%s" media-type="application/xhtml+xml"/>' % (i, c["file"])
              for i, c in enumerate(chapters, 1)]
    items += ['<item id="img%d" href="images/%s" media-type="%s"/>'
              % (i, name, IMAGE_TYPES[os.path.splitext(name)[1].lower()]) for i, name in enumerate(images, 1)]
    authors = []
    for c in chapters:
        if c["author"] not in authors:
            authors.append(c["author"])
    meta = ['<dc:identifier id="bookid">%s</dc:identifier>' % book_id,
            "<dc:title>%s</dc:title>" % esc(book["title"]), "<dc:language>%s</dc:language>" % esc(lang)]
    meta += ["<dc:creator>%s</dc:creator>" % esc(a) for a in authors]
    if book.get("date"):
        meta.append("<dc:date>%s</dc:date>" % esc(book["date"]))
    meta.append('<meta property="dcterms:modified">%s</meta>' % now)
    if cover:
        meta.append('<meta name="cover" content="cover-image"/>')
    opf = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="%s">\n'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n%s\n</metadata>\n'
           "<manifest>\n%s\n</manifest>\n"
           '<spine toc="ncx">\n<itemref idref="nav"/>\n%s\n</spine>\n'
           '<guide>\n<reference type="toc" title="Contents" href="nav.xhtml"/>\n'
           '<reference type="text" title="Start" href="%s"/>\n</guide>\n</package>\n'
           % (esc(lang, True), "\n".join(meta), "\n".join(items),
              "\n".join('<itemref idref="ch%d"/>' % i for i in range(1, len(chapters) + 1)), chapters[0]["file"]))
    ncx = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n<head>\n'
           '<meta name="dtb:uid" content="%s"/>\n<meta name="dtb:depth" content="1"/>\n'
           '<meta name="dtb:totalPageCount" content="0"/>\n<meta name="dtb:maxPageNumber" content="0"/>\n</head>\n'
           "<docTitle><text>%s</text></docTitle>\n<navMap>\n%s\n</navMap>\n</ncx>\n"
           % (book_id, esc(book["title"]), "\n".join(
               '<navPoint id="np%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="%s"/></navPoint>'
               % (i, i, esc(c["title"]), c["file"]) for i, c in enumerate(chapters, 1))))
    container = ('<?xml version="1.0" encoding="utf-8"?>\n'
                 '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n<rootfiles>\n'
                 '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>\n'
                 "</rootfiles>\n</container>\n")

    pages = [("nav.xhtml", nav)] + [(c["file"], c["page"]) for c in chapters]
    for name, text in pages + [("content.opf", opf), ("toc.ncx", ncx)]:
        try:
            minidom.parseString(text.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise SystemExit("%s is not well-formed XML: %s" % (name, exc))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with zipfile.ZipFile(out_path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, text in [("META-INF/container.xml", container), ("OEBPS/content.opf", opf),
                           ("OEBPS/toc.ncx", ncx), ("OEBPS/style.css", CSS.strip() + "\n")]:
            z.writestr(name, text, compress_type=zipfile.ZIP_DEFLATED)
        for name, text in pages:
            z.writestr("OEBPS/" + name, text, compress_type=zipfile.ZIP_DEFLATED)
        for name, path in images.items():
            z.write(path, "OEBPS/images/" + name, compress_type=zipfile.ZIP_STORED)
        if cover and os.path.basename(cover) not in images:
            z.write(cover, "OEBPS/images/" + os.path.basename(cover), compress_type=zipfile.ZIP_STORED)

    for c in chapters:
        print("%s  %5d words  %2d images  %s" % (c["file"], c["words"], c["images"], c["title"]))
    print("%s  %.1f MB" % (out_path, os.path.getsize(out_path) / 1e6))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    build(sys.argv[1], sys.argv[2])
