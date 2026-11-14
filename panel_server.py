#!/usr/bin/env python3
"""Simple HTTP server for DispWatter panel - serves panel/ directory on port 3000."""

import http.server
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PANEL_ROOT = os.path.join(SCRIPT_DIR, "panel")


class PanelHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PANEL_ROOT, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def translate_path(self, path):
        # Strip query params for file lookup
        path = path.split("?")[0]
        return super().translate_path(path)

    def log_message(self, format, *args):
        # Suppress default logging to stderr
        pass


if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", 3000), PanelHandler)
    print(f"DispWatter Panel server running on http://0.0.0.0:3000")
    sys.stdout.flush()
    server.serve_forever()
