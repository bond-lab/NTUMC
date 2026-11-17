#!/usr/bin/env bash
# Serve the corpus and wordnet site (display/) on this machine only.
#   bash scripts/serve_site.sh [PORT]      (default 8802)
set -euo pipefail
cd "$(dirname "$0")/../display"
exec python3 - "${1:-8802}" <<'PYEOF'
import http.server
import sys


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serve .gz files as raw bytes, so the browser does not decompress them."""

    def guess_type(self, path):
        if str(path).endswith(".gz"):
            return "application/octet-stream"
        return super().guess_type(path)


port = int(sys.argv[1])
print(f"Serving at http://localhost:{port}", flush=True)
http.server.test(HandlerClass=Handler, port=port, bind="127.0.0.1")
PYEOF
