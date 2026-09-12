#!/usr/bin/env python3
"""Serve the dashboard with closed R/As read live from TSD on every page load.

    ~/.venvs/tsd/bin/python serve_dashboard.py            # opens http://127.0.0.1:8765/
    ~/.venvs/tsd/bin/python serve_dashboard.py --host 0.0.0.0 --port 8080 --no-browser

Routes
    /                      index.html (built by refresh_dashboard.py)
    /api/closedrentals     JSON {pushedAt, source: "tsd", rows: [{date, location, count, month}]}
                           straight from TSD, same shape as the old worker feed, so the
                           page swaps sources without changing how it counts. EWRCON is
                           included as its own code and the page folds it into EWR.

When the page is served from here it fetches api/closedrentals on the same origin
first and only falls back to the worker if that fails. Results are cached in
memory for --cache-seconds (default 60) so a burst of reloads is one TSD query.
Nothing in the JSON is customer data: daily counts per branch code only.
"""
import argparse
import json
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from tsd_closed_ras import DEFAULT_SINCE, fetch_rows, read_credentials

HERE = Path(__file__).resolve().parent
INDEX = HERE / 'index.html'

_cache = {'at': 0.0, 'body': None}
_lock = threading.Lock()
CACHE_SECONDS = 60


def closed_rentals_json():
    """The feed body, refreshed from TSD when the cache is older than CACHE_SECONDS."""
    with _lock:
        if _cache['body'] is not None and time.time() - _cache['at'] < CACHE_SECONDS:
            return _cache['body']
        t0 = time.time()
        rows = fetch_rows(DEFAULT_SINCE)
        payload = {
            'pushedAt': datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
            'source': 'tsd',
            'rows': [{'date': d, 'location': loc, 'count': n, 'month': d[:7]} for d, loc, n in rows],
        }
        body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        _cache.update(at=time.time(), body=body)
        print(f'{datetime.now():%H:%M:%S} TSD query: {len(rows):,} rows in {time.time() - t0:.1f}s', flush=True)
        return body


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path == '/api/closedrentals':
            try:
                body = closed_rentals_json()
            except SystemExit as e:
                return self.fail(500, str(e))
            except Exception as e:
                return self.fail(502, f'TSD query failed: {e}')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if path == '/':
            self.path = '/index.html'
        # Only the page itself is served; the repo's scripts, CSV and PDF are not.
        if self.path != '/index.html':
            return self.fail(404, 'not found')
        return super().do_GET()

    def fail(self, code, msg):
        body = json.dumps({'error': msg}).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        print(f'{datetime.now():%H:%M:%S} {code} {msg}', file=sys.stderr)

    def log_message(self, fmt, *args):
        if '/api/' not in (args[0] if args else ''):
            return  # keep the console to TSD queries and errors
        super().log_message(fmt, *args)


def main():
    global CACHE_SECONDS
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--host', default='127.0.0.1', help='bind address (0.0.0.0 to share on the network)')
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--cache-seconds', type=int, default=CACHE_SECONDS,
                    help='reuse a TSD result for this long before querying again')
    ap.add_argument('--no-browser', action='store_true')
    args = ap.parse_args()
    CACHE_SECONDS = args.cache_seconds

    if not INDEX.exists():
        sys.exit(f'{INDEX.name} not found — run ./refresh_dashboard.py once to build it.')
    read_credentials()  # fail early with a clear message if the file is missing
    try:
        closed_rentals_json()  # fail early if TSD is unreachable
    except Exception as e:
        sys.exit(f'Could not query TSD: {e}')

    server = HTTPServer((args.host, args.port), Handler)
    url = f'http://{"127.0.0.1" if args.host == "0.0.0.0" else args.host}:{args.port}/'
    print(f'Dashboard at {url}  (closed R/As live from TSD, EWRCON under EWR; Ctrl+C to stop)', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nstopped')


if __name__ == '__main__':
    main()
