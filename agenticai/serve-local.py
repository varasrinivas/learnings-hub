#!/usr/bin/env python3
"""Serve the agenticai.varasrinivas.com catalog locally, from the real repos.

The catalog links to `courses/<slug>/index.html`, which only resolves on the
deployed site. Locally each course lives in its own sibling repo, in its own
layout. This server maps the deployed URL structure onto those real
directories, so the canonical `index.html` works unmodified.

Nothing is copied. There is no second landing page to drift out of sync: what
you see here is the exact file that deploys to the bucket root.

    python serve-local.py            # http://127.0.0.1:8000
    python serve-local.py -p 9000    # pick a port
    python serve-local.py --open     # also open a browser

Courses whose repo is not checked out are reported at startup and return a
readable 404 explaining which repo is missing, rather than a bare error.
"""
from __future__ import annotations

import argparse
import http.server
import posixpath
import socketserver
import sys
import urllib.parse
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent          # …/learnings-hub/agenticai
REPOS = HERE.parent.parent                       # …/tutorials/repo
FLAGSHIP = REPOS / "claude-agent-course-final-adv" / "output"

# URL prefix -> directory on disk. Longest prefix wins, so the `walkthrough`
# entries must be able to beat their parent course; `_match` sorts by length.
ROUTES: dict[str, Path] = {
    "/courses/claude-agents/":        FLAGSHIP / "courses" / "claude-agents",
    "/courses/cc/":                   FLAGSHIP / "courses" / "cc",
    "/courses/mcp/":                  FLAGSHIP / "courses" / "mcp",
    "/courses/gemini-cli/":           FLAGSHIP / "courses" / "gemini-cli",
    "/courses/gemini-code-assist/":   FLAGSHIP / "courses" / "gemini-code-assist",
    "/courses/opensource/":           FLAGSHIP / "courses" / "opensource",
    "/courses/multi-sdk-agents/":     FLAGSHIP / "courses" / "multi-sdk-agents",
    "/courses/ai-cli-comparison/":    FLAGSHIP / "courses" / "ai-cli-comparison",
    "/mobile/":                       FLAGSHIP / "mobile",

    "/courses/context-engineering/walkthrough/":    REPOS / "context-eng-kit" / "walkthrough",
    "/courses/context-engineering/":                REPOS / "context-eng-kit" / "course",
    "/courses/knowledge-graph/walkthrough/":        REPOS / "knowledge-graph" / "walkthrough",
    "/courses/knowledge-graph/":                    REPOS / "knowledge-graph" / "output",
    "/courses/ultimate-context-eng/walkthrough/":   REPOS / "ultimate-context-eng" / "walkthrough",
    "/courses/ultimate-context-eng/":               REPOS / "ultimate-context-eng" / "course",
    "/courses/spec-driven-development/walkthrough/": REPOS / "priorauth-sdd-course" / "walkthrough",
    "/courses/spec-driven-development/":            REPOS / "priorauth-sdd-course",

    "/courses/llmops/course/walkthrough/":           REPOS / "llmops-kit" / "walkthrough",
    # Repo root, not course/: the catalog opens llmops-course-map.html, which
    # sits beside course/index.html on the site but above it in the repo.
    "/courses/llmops/":                             REPOS / "llmops-kit",
    "/courses/ai-platform-engineering/walkthrough/": REPOS / "ai-platform-kit" / "walkthrough",
    "/courses/ai-platform-engineering/":            REPOS / "ai-platform-kit" / "course",
    "/courses/code-with-ai/":                        REPOS / "campuscrave-kit",

    # The four OpenSpec pages are single files in the AI-SDLC build output,
    # renamed on deploy — see ALIASES, and ALIAS_ONLY below. The lab bundles and
    # their downloads page are assembled by that repo's deploy build.
    "/courses/openspec/labs/":                       REPOS / "ai-sdlc-course-final" / "scripts" / "dist" / "courses" / "openspec" / "labs",
    "/courses/openspec/":                            REPOS / "ai-sdlc-course-final" / "output",
}

# Where a course's landing file isn't literally named index.html on disk.
ALIASES: dict[str, str] = {
    "/courses/spec-driven-development/index.html": "spec-driven-development-guide.html",
    "/courses/openspec/index.html":                "ai-sdlc-openspec-course.html",
    "/courses/openspec/frontend.html":             "ai-sdlc-openspec-frontend-course.html",
    "/courses/openspec/api.html":                  "ai-sdlc-openspec-api-course.html",
    "/courses/openspec/data.html":                 "ai-sdlc-openspec-data-course.html",
}

# Routes that serve their ALIASES entries and nothing else. `/courses/openspec/`
# points at the shared AI-SDLC output directory, which also holds twenty
# unrelated courses; without this they would all be reachable under that prefix.
ALIAS_ONLY: frozenset[str] = frozenset({"/courses/openspec/"})

# Routes served out of a build tree rather than checked-in files: present only
# after the owning repo's build has run. Names the command that produces them.
NEEDS_BUILD: dict[str, str] = {
    "/courses/openspec/labs/":
        "cd ../../ai-sdlc-course-final && python scripts/build_openspec_site.py",
}

# Which repo to name when a route's directory is absent.
REPO_OF = {
    "/mobile/": "claude-agent-course-final-adv",
    "/courses/context-engineering/": "context-eng-kit",
    "/courses/knowledge-graph/": "knowledge-graph",
    "/courses/ultimate-context-eng/": "ultimate-context-eng",
    "/courses/spec-driven-development/": "priorauth-sdd-course",
    "/courses/llmops/": "llmops-kit",
    "/courses/ai-platform-engineering/": "ai-platform-kit",
    "/courses/code-with-ai/": "campuscrave-kit",
    "/courses/openspec/": "ai-sdlc-course-final",
}


def _repo_for(prefix: str) -> str:
    for known, repo in REPO_OF.items():
        if prefix.startswith(known):
            return repo
    return "claude-agent-course-final-adv"


def _match(urlpath: str) -> tuple[str, Path] | None:
    for prefix in sorted(ROUTES, key=len, reverse=True):
        if urlpath.startswith(prefix):
            return prefix, ROUTES[prefix]
    return None


class CatalogHandler(http.server.SimpleHTTPRequestHandler):
    """Maps deployed-site URLs onto the local repos."""

    missing_prefix: str | None = None
    needs_build: tuple[str, str] | None = None

    def translate_path(self, path: str) -> str:
        self.missing_prefix = None
        self.needs_build = None

        urlpath = urllib.parse.urlsplit(path).path
        urlpath = urllib.parse.unquote(urlpath, errors="surrogatepass")

        # Collapse . and .. before routing so traversal can't escape a route.
        parts = [p for p in urlpath.split("/") if p not in ("", ".")]
        safe: list[str] = []
        for part in parts:
            if part == "..":
                if safe:
                    safe.pop()
            else:
                safe.append(part)
        urlpath = "/" + "/".join(safe)
        if path.endswith("/") and not urlpath.endswith("/"):
            urlpath += "/"
        if urlpath.endswith("/"):
            urlpath += "index.html"

        # The catalog itself.
        if urlpath in ("/index.html", "/"):
            return str(HERE / "index.html")

        alias = ALIASES.get(urlpath)
        hit = _match(urlpath)
        if hit is None:
            return str(HERE / "__no_route__")

        prefix, root = hit
        if prefix in ALIAS_ONLY and alias is None:
            return str(HERE / "__no_route__")
        if not root.is_dir():
            if prefix in NEEDS_BUILD:
                self.needs_build = (prefix, NEEDS_BUILD[prefix])
                return str(HERE / "__needs_build__")
            self.missing_prefix = prefix
            return str(HERE / "__missing_repo__")

        rel = alias if alias else urlpath[len(prefix):]
        target = (root / rel).resolve()

        # Never serve outside the matched route.
        try:
            target.relative_to(root.resolve())
        except ValueError:
            return str(HERE / "__no_route__")
        return str(target)

    def send_error(self, code, message=None, explain=None):  # noqa: N802
        if code == 404 and self.needs_build:
            prefix, command = self.needs_build
            body = (
                f"<h1>Not built yet</h1>"
                f"<p><code>{prefix}</code> is served from a build tree that "
                f"hasn't been produced on this machine. Build it with:</p>"
                f"<pre>{command}</pre>"
                f"<p>then reload. Every other course still works.</p>"
                f'<p><a href="/">&larr; back to the catalog</a></p>'
            ).encode("utf-8")
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        if code == 404 and self.missing_prefix:
            repo = _repo_for(self.missing_prefix)
            body = (
                f"<h1>Course not checked out locally</h1>"
                f"<p><code>{self.missing_prefix}</code> is served from the "
                f"<b>{repo}</b> repo, which isn't present at "
                f"<code>{REPOS}</code>.</p>"
                f"<p>Clone it as a sibling of <code>learnings-hub</code>, or "
                f"just skip this card — every other course still works.</p>"
                f'<p><a href="/">&larr; back to the catalog</a></p>'
            ).encode("utf-8")
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        super().send_error(code, message, explain)

    def list_directory(self, path):
        # No directory listings — this mirrors a static site, and listings
        # would expose repo internals that never ship.
        self.send_error(404, "No directory listing")
        return None

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))


def report() -> int:
    print(f"\n  catalog   {HERE / 'index.html'}")
    print(f"  repos     {REPOS}\n")
    missing = 0
    for prefix in sorted(ROUTES):
        root = ROUTES[prefix]
        if root.is_dir():
            print(f"  [ok]      {prefix}")
        elif prefix in NEEDS_BUILD:
            missing += 1
            print(f"  [UNBUILT] {prefix}  <- run: {NEEDS_BUILD[prefix]}")
        else:
            missing += 1
            print(f"  [MISSING] {prefix}  <- {_repo_for(prefix)} not checked out")
    return missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--port", type=int, default=8000)
    ap.add_argument("--open", action="store_true", help="open a browser")
    args = ap.parse_args()

    if not (HERE / "index.html").is_file():
        print(f"error: {HERE / 'index.html'} not found", file=sys.stderr)
        return 1

    missing = report()
    url = f"http://127.0.0.1:{args.port}/"
    print(f"\n  serving   {url}")
    if missing:
        print(f"  note      {missing} course(s) unavailable locally; the rest work")
    print("  stop      Ctrl+C\n")

    if args.open:
        webbrowser.open(url)

    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("127.0.0.1", args.port), CatalogHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped\n")
    except OSError as exc:
        print(f"\n  error: cannot bind port {args.port}: {exc}\n", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
