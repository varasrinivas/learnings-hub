# Learnings — courses hub

The landing page for **[learnings.varasrinivas.com](https://learnings.varasrinivas.com/)** — a single
page that collates the available courses as cards and links into each one.

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
| Data Engineering with PySpark | [`/data-engineering-course/`](https://learnings.varasrinivas.com/data-engineering-course/) | [data-engineering-course](https://github.com/varasrinivas/data-engineering-course) |
| Data Engineering Core — Interview-Ready | [`/data-engineering-fundamentals/`](https://learnings.varasrinivas.com/data-engineering-fundamentals/) | [data-engineering-fundamentals-course](https://github.com/varasrinivas/data-engineering-fundamentals-course) |
| The 10x Toolkit — Claude Code, Copilot & Cursor | [`/the-full-ai-course/`](https://learnings.varasrinivas.com/the-full-ai-course/) | [the-full-ai-tools-course](https://github.com/varasrinivas/the-full-ai-tools-course) |

## Adding a course
Each course lives under its own top-level folder in the site bucket. To list a new one, add a `<a class="card">`
block in `index.html` (chip, title, description, tags, link to the course folder) and redeploy.

## Deploy
The site is served from the S3 bucket behind CloudFront for `learnings.varasrinivas.com`. This file is the
bucket-root object:
```bash
aws s3 cp index.html s3://learnings.varasrinivas.com/index.html \
  --content-type "text/html; charset=utf-8" --cache-control "public, max-age=300"
aws cloudfront create-invalidation --distribution-id ESC8HMAS41DRF --paths "/*"
```
