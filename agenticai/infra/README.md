# infra — how agenticai.varasrinivas.com resolves URLs

The site is one S3 bucket (`agenticai.varasrinivas.com`) behind CloudFront
(`E204WFPQTUDQ3Q`), with the **S3 REST endpoint** as origin, locked down by an
Origin Access Control. That origin choice drives everything below.

## Why a function is needed at all

The REST endpoint is not a website endpoint: it serves objects by exact key and
has **no index-document behaviour**. `/courses/mcp/` is not a key, so it misses.
And because the OAC policy grants `GetObject` only — no `ListBucket` — a miss
comes back as **403, not 404**.

`cloudfront-function.js` (viewer-request, deployed as `agenticai-legacy-redirects`)
does two jobs:

1. **Legacy 301s** — pre-June-2026 flat-layout URLs to the `/courses/` structure,
   including the CC module renumbering.
2. **Directory resolution** — `/courses/mcp/` → `/courses/mcp/index.html`, and
   `/courses/mcp` → 301 → `/courses/mcp/`. Every object in the bucket has a file
   extension, so a last path segment with no dot is always a folder.

Two root pages are excluded from the flat-layout rule because they genuinely
live at the root: `/index.html` and `/404.html`. Forgetting `/404.html` makes the
error page redirect to a course folder — worth remembering if more root pages
are ever added.

## Error handling

Because every miss surfaces as 403, the distribution maps **both 403 and 404** to
`/404.html` with response code **404**.

This replaced a `403 → /index.html` with response code **200**, which meant every
bad URL rendered the catalog as a success — `/courses/nonexistent/` looked like a
real page to a reader and like a valid page to a crawler. Custom error pages are
fetched from the origin directly, so the viewer-request function does not run for
them; `/404.html` must exist as a real object at the bucket root.

## Deploying a change

The function source here is the source of truth — edit it, then:

```bash
cd learnings-hub/agenticai
ETAG=$(aws cloudfront describe-function --name agenticai-legacy-redirects --query ETag --output text)
aws cloudfront update-function --name agenticai-legacy-redirects --if-match "$ETAG" \
    --function-config '{"Comment":"301s from old flat layout, plus directory-index resolution for the S3 REST origin","Runtime":"cloudfront-js-2.0"}' \
    --function-code fileb://infra/cloudfront-function.js
```

**Always test before publishing.** `update-function` only touches the DEVELOPMENT
stage, so live traffic is unaffected until `publish-function`:

```bash
DETAG=$(aws cloudfront describe-function --name agenticai-legacy-redirects --stage DEVELOPMENT --query ETag --output text)
# event object must nest the request: {"version":"1.0","context":{...},"viewer":{...},"request":{"uri":"/courses/mcp/",...}}
MSYS_NO_PATHCONV=1 aws cloudfront test-function --name agenticai-legacy-redirects \
    --if-match "$DETAG" --stage DEVELOPMENT --event-object fileb://event.json
aws cloudfront publish-function --name agenticai-legacy-redirects --if-match "$DETAG"
```

Under Git Bash, `MSYS_NO_PATHCONV=1` is required for anything passing a
leading-slash URI, or `/courses/mcp/` is rewritten to a Windows path before it
reaches the function and the test silently exercises the wrong URI.

The `404.html` beside this directory deploys like the catalog — a single
`aws s3 cp` to the bucket root, never a sync with `--delete`.
