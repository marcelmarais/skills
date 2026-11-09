# kindle-reads

An agent skill that finds a few fresh, good articles, packages the complete originals and their images into one clean EPUB, and emails it to your Kindle.

- [SKILL.md](SKILL.md): how the agent chooses, captures, checks and sends.
- [scripts/build_epub.py](scripts/build_epub.py): builds the EPUB from a JSON manifest and HTML fragments. Python 3 standard library only.

## Install

Clone into your agent's skills folder, for example:

```bash
git clone https://github.com/<owner>/kindle-reads ~/.claude/skills/kindle-reads
```

Then ask for it: "Find four good articles from the last day for my Kindle."

The agent needs a browser signed in to X (for Grok) and to your mail, `ffmpeg` for images, and your Kindle address with an approved sender. Addresses come from your request; none are stored in the skill.

## Build an EPUB by hand

```bash
python3 scripts/build_epub.py book.json out/reads.epub
```

The manifest format is documented at the top of the script. The build fails on remote images, video and other content it cannot embed, so nothing is dropped silently.

## Content

The EPUBs contain other people's writing in full. They are for your own reading; keep them private.
