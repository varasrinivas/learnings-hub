#!/usr/bin/env python3
"""
Publish the courses hub to S3 and invalidate the CloudFront cache.

index.html is the bucket-root object for learnings.varasrinivas.com, so a
deploy is one PUT plus one cache invalidation:

    index.html
      -> s3://<bucket>/index.html
      -> invalidate / and /index.html
      -> https://<domain>/

Before uploading it checks the page itself. The failure that actually matters
for a landing page is a card pointing at a course that is not deployed, so
every internal link is resolved against the bucket -- "spring-boot-course/"
must have a real spring-boot-course/index.html behind it. Tag balance and the
working tree are checked too.

The upload is skipped when the deployed file already matches the local one, so
re-running is safe and cheap.

Usage:
    python deploy.py                  # check, upload, invalidate
    python deploy.py --dry-run        # print every step, change nothing
    python deploy.py --strict         # refuse to deploy on any warning
    python deploy.py --force          # upload even if S3 is already current
    python deploy.py --skip-checks    # skip the page checks

Requires the AWS CLI on PATH with credentials that can write the bucket and
create invalidations.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAGE = ROOT / "index.html"

# Deploy target. These match the live site; override with the flags below.
BUCKET = "learnings.varasrinivas.com"
KEY = "index.html"
DISTRIBUTION = "ESC8HMAS41DRF"
DOMAIN = "learnings.varasrinivas.com"

CONTENT_TYPE = "text/html; charset=utf-8"
CACHE_CONTROL = "public, max-age=300"
RELEASE_BRANCH = "main"

# Void elements, plus the SVG shapes this page uses -- none of these close.
VOID = {"meta", "link", "br", "img", "hr", "input", "source", "area", "col",
        "embed", "param", "track", "wbr", "path", "circle", "rect", "line",
        "polygon", "polyline", "ellipse", "use", "stop"}

problems, warnings = [], []


def err(m):
    problems.append(m)


def warn(m):
    warnings.append(m)


def run(cmd, check=True):
    """Run a command and return (returncode, stdout). Never raises on non-zero."""
    # Pin both ends to UTF-8 so a cp1252 console on Windows cannot mangle output.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    if check and p.returncode != 0:
        sys.stderr.write((p.stderr or p.stdout or "").strip() + "\n")
    return p.returncode, (p.stdout or "").strip()


def git(*args):
    code, out = run(["git", "-C", str(ROOT), *args], check=False)
    return out if code == 0 else None


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Balance(HTMLParser):
    """Track open tags so an unclosed <div> cannot ship silently."""

    def __init__(self):
        super().__init__()
        self.stack = []
        self.mismatched = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass
            self.mismatched.append(tag)


def internal_links(html: str):
    """Every same-site href, as (href, s3 key) pairs. Fragments and external
    links are dropped; a bare "foo/" resolves to the folder's index.html."""
    out = {}
    for href in re.findall(r'href="([^"]+)"', html):
        if href.startswith(("http://", "https://", "#", "mailto:", "//")):
            continue
        path = href.split("#", 1)[0].strip()
        if not path or path == "/":
            continue
        key = path.lstrip("/")
        if key.endswith("/"):
            key += "index.html"
        out.setdefault(key, href)
    return sorted(out.items())


def page_checks(html: str, bucket: str, check_links: bool):
    b = Balance()
    b.feed(html)
    if b.stack:
        err(f"unclosed tag(s) at end of document: {', '.join(b.stack[:5])}")
    if b.mismatched:
        err(f"mismatched closing tag(s): {', '.join(sorted(set(b.mismatched))[:5])}")

    cards = len(re.findall(r'<a class="card(?:-main)?"', html))
    print(f"Cards         : {cards}")

    links = internal_links(html)
    print(f"Internal links: {len(links)}")
    if not check_links:
        print("               (not resolved -- --skip-linkcheck)")
        return

    missing = []
    for key, href in links:
        code, _ = run(["aws", "s3api", "head-object", "--bucket", bucket,
                       "--key", key, "--query", "ETag", "--output", "text"],
                      check=False)
        if code != 0:
            missing.append((href, key))
    if missing:
        for href, key in missing:
            err(f'dead link: href="{href}" -> s3://{bucket}/{key} does not exist')
    else:
        print(f"               all {len(links)} resolve in the bucket")


def git_checks():
    """Warn about anything that would make this deploy hard to trace back."""
    if git("rev-parse", "--git-dir") is None:
        warn("not a git repository -- cannot record what was deployed.")
        return

    if git("status", "--porcelain"):
        warn("working tree has uncommitted changes -- deploying content that is "
             "not committed anywhere.")

    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch and branch != RELEASE_BRANCH:
        warn(f'on branch "{branch}", not "{RELEASE_BRANCH}".')

    counts = git("rev-list", "--left-right", "--count", f"HEAD...origin/{branch}")
    if counts:
        ahead, _, behind = counts.partition("\t")
        if ahead.strip() != "0":
            warn(f"{ahead.strip()} commit(s) not pushed to origin/{branch} -- the "
                 f"deployed content would not be on the remote.")
        if behind.strip() != "0":
            warn(f"{behind.strip()} commit(s) behind origin/{branch} -- you may be "
                 f"deploying stale content.")


def remote_etag(bucket: str, key: str):
    """Return the deployed object's ETag, or None if it is not there yet."""
    code, out = run(["aws", "s3api", "head-object",
                     "--bucket", bucket, "--key", key,
                     "--query", "ETag", "--output", "text"], check=False)
    if code != 0:
        return None
    return out.strip().strip('"')


def main() -> int:
    # A cp1252 console must not turn a successful deploy into a traceback.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Deploy the courses hub to S3 + CloudFront.")
    ap.add_argument("--bucket", default=BUCKET, help=f"S3 bucket (default: {BUCKET})")
    ap.add_argument("--key", default=KEY, help=f"object key (default: {KEY})")
    ap.add_argument("--distribution", default=DISTRIBUTION,
                    help=f"CloudFront distribution id (default: {DISTRIBUTION})")
    ap.add_argument("--file", default=str(PAGE), help="file to publish (default: index.html)")
    ap.add_argument("--dry-run", action="store_true", help="print each step, change nothing")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures")
    ap.add_argument("--force", action="store_true", help="upload even if S3 already matches")
    ap.add_argument("--skip-checks", action="store_true", help="skip the page checks")
    ap.add_argument("--skip-linkcheck", action="store_true",
                    help="check the markup but do not resolve links against the bucket")
    ap.add_argument("--no-invalidate", action="store_true", help="skip the CloudFront invalidation")
    args = ap.parse_args()

    src = Path(args.file)
    url = f"https://{DOMAIN}/"

    if not src.exists():
        print(f"ERROR: nothing to deploy at {src}", file=sys.stderr)
        return 2
    if shutil.which("aws") is None:
        print("ERROR: the AWS CLI is not on PATH.", file=sys.stderr)
        return 2

    # --- preflight -------------------------------------------------------
    if not args.skip_checks:
        print("Checking the page ...")
        page_checks(src.read_text(encoding="utf-8"), args.bucket, not args.skip_linkcheck)

    git_checks()

    if warnings or problems:
        print()
        for w in warnings:
            print("WARN:", w)
        for p in problems:
            print("FAIL:", p)
    if problems:
        print(f"\nERROR: {len(problems)} problem(s) -- not deploying.", file=sys.stderr)
        return 1
    if warnings and args.strict:
        print(f"\nERROR: --strict and {len(warnings)} warning(s) -- not deploying.",
              file=sys.stderr)
        return 1

    # --- is the deploy even needed? --------------------------------------
    local = md5(src)
    deployed = remote_etag(args.bucket, args.key)
    print(f"\nSource   : {src.name} ({src.stat().st_size:,} bytes, md5 {local[:12]}...)")
    print(f"Target   : s3://{args.bucket}/{args.key}")

    if deployed is None:
        print("Deployed : (not present -- first deploy)")
    elif "-" in deployed:
        # Multipart upload: the ETag is not a plain md5, so we cannot compare.
        print(f"Deployed : multipart ETag {deployed} -- cannot compare, uploading.")
        deployed = None
    else:
        print(f"Deployed : md5 {deployed[:12]}...")

    if deployed == local and not args.force:
        print("\nAlready current -- nothing to upload. (Use --force to re-upload.)")
        print(f"Live at  : {url}")
        return 0

    # --- upload ----------------------------------------------------------
    upload = ["aws", "s3", "cp", str(src), f"s3://{args.bucket}/{args.key}",
              "--content-type", CONTENT_TYPE, "--cache-control", CACHE_CONTROL]
    # Only the root object changes, so invalidate it rather than the whole site --
    # a blanket /* would evict every course for no reason.
    paths = ["/", f"/{args.key}"]
    if args.dry_run:
        print("\n[dry-run] would run:")
        print("  " + " ".join(upload))
        if not args.no_invalidate:
            print(f"  aws cloudfront create-invalidation --distribution-id "
                  f"{args.distribution} --paths {' '.join(paths)}")
        return 0

    print("\nUploading ...")
    code, _ = run(upload)
    if code != 0:
        print("ERROR: upload failed.", file=sys.stderr)
        return 1

    # Read it back: the deployed ETag must equal the local md5.
    confirmed = remote_etag(args.bucket, args.key)
    if confirmed != local:
        print(f"ERROR: uploaded, but the deployed ETag ({confirmed}) does not match "
              f"the local md5 ({local}).", file=sys.stderr)
        return 1
    print("OK: uploaded and verified (ETag matches local md5).")

    # --- invalidate ------------------------------------------------------
    if args.no_invalidate:
        print("\nSkipped the invalidation -- CloudFront may serve the old page for "
              "up to the cache lifetime.")
    else:
        print("Invalidating CloudFront ...")
        # subprocess passes argv straight through, so Git Bash cannot rewrite
        # "/index.html" into a Windows path (no MSYS_NO_PATHCONV needed here).
        code, out = run(["aws", "cloudfront", "create-invalidation",
                         "--distribution-id", args.distribution,
                         "--paths", *paths, "--output", "json"])
        if code != 0:
            print("ERROR: upload succeeded but the invalidation failed. The new page "
                  "is in S3; re-run to retry the invalidation.", file=sys.stderr)
            return 1
        inv = json.loads(out)["Invalidation"]
        print(f"OK: invalidation {inv['Id']} ({inv['Status']}).")

    commit = git("rev-parse", "--short", "HEAD")
    print(f"\nDeployed{' ' + commit if commit else ''} -> {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
