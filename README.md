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

## Adding a course
Each course lives under its own top-level folder in the site bucket. To list a new one, add a `<a class="card">`
block in `index.html` (chip, title, description, tags, link to the course folder) and redeploy.

## Deploy
The site is served from the S3 bucket behind CloudFront for `learnings.varasrinivas.com`. This file is the
bucket-root object:
```bash
aws s3 cp index.html s3://learnings.varasrinivas.com/index.html \
  --content-type "text/html; charset=utf-8" --cache-control "public, max-age=300"
aws cloudfront create-invalidation --distribution-id <DIST_ID> --paths "/*"
```
