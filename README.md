# Learnings — courses hub

The landing page for **[learnings.varasrinivas.com](https://learnings.varasrinivas.com/)** — a single
page that collates the available courses as cards and links into each one.

Also home to **`agenticai/index.html`** — the canonical source of the
[agenticai.varasrinivas.com](https://agenticai.varasrinivas.com/) landing page (bucket-root object of
the `agenticai.varasrinivas.com` S3 bucket, CloudFront `E204WFPQTUDQ3Q`). It groups the 15 AI-agent
courses into six tracks, shows a suggested learning path, and prints each course's site path on its
card. Deploy by hand: `aws s3 cp agenticai/index.html s3://agenticai.varasrinivas.com/index.html
--content-type "text/html; charset=utf-8" --cache-control "public, max-age=300"` then invalidate
`/` and `/index.html` on `E204WFPQTUDQ3Q` (use `MSYS_NO_PATHCONV=1` under Git Bash).

### Previewing it locally

The catalog links to `courses/<slug>/index.html`, which only resolves on the deployed site — locally
each course lives in its own sibling repo, in its own layout. `agenticai/serve-local.py` maps the
deployed URL structure onto those real directories:

```bash
python agenticai/serve-local.py          # http://127.0.0.1:8000
python agenticai/serve-local.py --open   # and open a browser
```

Nothing is copied and there is no second landing page to drift — it serves the same
`agenticai/index.html` that deploys to the bucket root, so what you click through locally is what
ships. Because the URLs match production, cross-course links inside modules (`../code-with-ai/`)
resolve too, which a plain `python -m http.server` cannot do.

Courses whose repo isn't checked out are listed at startup and return a readable 404 naming the
missing repo, so a partial checkout still previews everything else. Sibling repos it expects:
`claude-agent-course-final-adv`, `campuscrave-kit`, `context-eng-kit`, `knowledge-graph`,
`ultimate-context-eng`, `priorauth-sdd-course`, `llmops-kit`, `ai-platform-kit`.

A standalone `index.html`: no build step, no dependencies (web fonts only), dark theme matching the
courses, responsive, and accessible (honors `prefers-reduced-motion`).

## Courses linked
| Course | Path | Repo |
|--------|------|------|
| Java for Developers | [`/java-fundamentals-course/`](https://learnings.varasrinivas.com/java-fundamentals-course/) | [java-fundamentals-course](https://github.com/varasrinivas/java-fundamentals-course) |
| Python for Java Developers | [`/python-java-course/`](https://learnings.varasrinivas.com/python-java-course/) | — |
| Spring Boot & Microservices | [`/spring-boot-course/`](https://learnings.varasrinivas.com/spring-boot-course/) | [spring-boot-course](https://github.com/varasrinivas/spring-boot-course) |
| AWS AI-DLC — Method, Engines & Leadership | [`/ai-dlc-course/`](https://learnings.varasrinivas.com/ai-dlc-course/) | [ai-dlc-course](https://github.com/varasrinivas/ai-dlc-course) |
| AI-DLC for Sprint Teams — Prior Auth Portal | [`/ai-dlc-sprint-teams/`](https://learnings.varasrinivas.com/ai-dlc-sprint-teams/) | [ai-dlc-sprint-teams](https://github.com/varasrinivas/ai-dlc-sprint-teams) |
| AI-DLC in Practice — The 76-Day Mandate | [`/ai-dlc-practical/`](https://learnings.varasrinivas.com/ai-dlc-practical/) | [ai-dlc-practical](https://github.com/varasrinivas/ai-dlc-practical) (companion lab repo) |
| Data Engineering with PySpark | [`/data-engineering-course/`](https://learnings.varasrinivas.com/data-engineering-course/) | [data-engineering-course](https://github.com/varasrinivas/data-engineering-course) |
| Data Engineering Core — Interview-Ready | [`/data-engineering-fundamentals/`](https://learnings.varasrinivas.com/data-engineering-fundamentals/) | [data-engineering-fundamentals-course](https://github.com/varasrinivas/data-engineering-fundamentals-course) |
| The 10x Toolkit — Claude Code, Copilot & Cursor | [`/the-full-ai-course/`](https://learnings.varasrinivas.com/the-full-ai-course/) | [the-full-ai-tools-course](https://github.com/varasrinivas/the-full-ai-tools-course) |
| Migrating Spring Boot 3.x → 4.0 with Claude Code (guide) | [`/spring-boot-4-migration-guide/`](https://learnings.varasrinivas.com/spring-boot-4-migration-guide/) | [ai-generated-guides](https://github.com/varasrinivas/ai-generated-guides) |
| Migrating Spring Boot 3.x → 4.0 with OpenAI Codex (guide) | [`/spring-boot-4-migration-guide-codex/`](https://learnings.varasrinivas.com/spring-boot-4-migration-guide-codex/) | [ai-generated-guides](https://github.com/varasrinivas/ai-generated-guides) |

## Adding a course
Each course lives under its own top-level folder in the site bucket. To list a new one, add a `<a class="card">`
block in `index.html` (chip, title, description, tags, link to the course folder) and redeploy. Deploy the
course itself first — `deploy.py` refuses to publish a card whose target folder isn't in the bucket yet.

## Deploy
The site is served from the S3 bucket behind CloudFront for `learnings.varasrinivas.com`. This file is the
bucket-root object. Use the script:
```bash
python deploy.py              # check, upload, invalidate
python deploy.py --dry-run    # show every step, change nothing
```
It resolves **every internal link against the bucket** before uploading — a card pointing at a course
folder that was never deployed fails the deploy instead of shipping a 404 — plus a tag-balance check and
the usual dirty-tree / unpushed-commit warnings. It skips the upload when the live page already matches,
verifies the deployed ETag against the local checksum, and invalidates `/` and `/index.html` rather than
`/*`, so the other courses stay cached.

Add `--strict` to turn the git warnings into a refusal. `--skip-linkcheck` skips the per-link S3 lookups
when you just want the markup checked. Overrides: `--bucket`, `--key`, `--distribution`.

**Deploys are run locally, never from GitHub Actions.** Automating this would mean putting AWS credentials
for the site's account into repository secrets — not worth the convenience. Run `python deploy.py` from a
machine that already has the credentials.

Doing it by hand instead:
```bash
aws s3 cp index.html s3://learnings.varasrinivas.com/index.html \
  --content-type "text/html; charset=utf-8" --cache-control "public, max-age=300"
# MSYS_NO_PATHCONV=1 stops Git Bash from rewriting "/*" into a Windows path
MSYS_NO_PATHCONV=1 aws cloudfront create-invalidation --distribution-id ESC8HMAS41DRF --paths "/*"
```
(`deploy.py` needs no such guard — it passes argv straight to `aws` with no shell in between.)
