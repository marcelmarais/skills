# skills

Agent skills. Each folder is one self-contained skill: a `SKILL.md` and any scripts it needs.

| Skill | What it does |
| --- | --- |
| [kindle-reads](kindle-reads/SKILL.md) | Finds a few fresh, good articles, packages the complete originals and their images into one clean EPUB, and emails it to your Kindle. |

## Install

Clone the repo, then link the skills you want into your agent's skills folder:

```bash
ln -s "$PWD/kindle-reads" ~/.claude/skills/kindle-reads
```

## Notes

- kindle-reads needs a browser signed in to X (for Grok) and to your mail, `ffmpeg` for images, and a Kindle address with an approved sender. Addresses come from your request; none are stored in the skill.
- The EPUBs it builds contain other people's writing in full. They are for your own reading; keep them private.
