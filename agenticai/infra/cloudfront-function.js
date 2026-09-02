// CloudFront Function (cloudfront-js-2.0, viewer-request) for agenticai.varasrinivas.com
// Deployed as "agenticai-legacy-redirects" on distribution E204WFPQTUDQ3Q.
//
// Two jobs:
//   1. 301-redirect pre-June-2026 flat-layout URLs to the /courses/ structure.
//   2. Resolve directory URLs. The origin is the S3 REST endpoint, which has no
//      index-document behaviour of its own, so /courses/mcp/ misses unless the
//      URI is rewritten to /courses/mcp/index.html here.
//
// Deploy with infra/deploy-cloudfront.sh (see infra/README.md).

function handler(event) {
    var request = event.request;
    var uri = request.uri;

    // CC modules that were renumbered when the course moved under /courses/cc/
    var ccRenames = {
        '/cc/CC1-claude-md-and-memory.html': '/courses/cc/CC3-claude-md-and-memory.html',
        '/cc/CC2-permissions-and-sandbox.html': '/courses/cc/CC4-permissions-and-sandbox.html',
        '/cc/CC3-skills-and-commands.html': '/courses/cc/CC5-skills-and-commands.html',
        '/cc/CC4-subagents.html': '/courses/cc/CC6-subagents.html',
        '/cc/CC5-hooks.html': '/courses/cc/CC7-hooks.html',
        '/cc/CC6-mcp.html': '/courses/cc/CC9-mcp.html',
        '/cc/CC7-power-user-and-cicd.html': '/courses/cc/CC14-power-user-and-cicd.html'
    };

    // Course folders that moved from the bucket root to /courses/<same-name>/
    var movedPrefixes = ['/ai-cli-comparison/', '/cc/', '/gemini-cli/', '/mcp/', '/opensource/'];

    var target = null;

    if (ccRenames[uri]) {
        target = ccRenames[uri];
    } else if (uri.startsWith('/interview/')) {
        target = '/courses/claude-agents' + uri;
    } else {
        for (var i = 0; i < movedPrefixes.length; i++) {
            if (uri.startsWith(movedPrefixes[i])) {
                target = '/courses' + uri;
                break;
            }
        }
        // Old flat layout: every root-level page now lives in the main course
        // folder — except the site's own root pages, which really do live there.
        if (!target && uri !== '/index.html' && uri !== '/404.html'
                && /^\/[^\/]+\.html$/.test(uri)) {
            target = '/courses/claude-agents' + uri;
        }
    }

    if (target) {
        return {
            statusCode: 301,
            statusDescription: 'Moved Permanently',
            headers: {
                'location': { value: target },
                'cache-control': { value: 'max-age=86400' }
            }
        };
    }

    // A folder URL with no trailing slash: /courses/mcp -> /courses/mcp/.
    // Redirect rather than rewrite so the browser's address bar ends up on the
    // canonical form, which keeps any relative links on the page resolving.
    // Every object in the bucket has a file extension, so a last segment with
    // no dot is always a folder, never a file.
    var last = uri.substring(uri.lastIndexOf('/') + 1);
    if (last !== '' && last.indexOf('.') === -1) {
        return {
            statusCode: 301,
            statusDescription: 'Moved Permanently',
            headers: {
                'location': { value: uri + '/' },
                'cache-control': { value: 'max-age=86400' }
            }
        };
    }

    // Directory index. Without this the S3 REST origin returns 403 for every
    // folder URL, which the distribution's error response used to serve as the
    // catalog with a 200.
    if (uri.endsWith('/')) {
        request.uri = uri + 'index.html';
    }

    return request;
}
