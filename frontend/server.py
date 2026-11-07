"""Plan4U Frontend Web Server running on Port 3000."""
import http.server
import socketserver
import os
import webbrowser

PORT = 3000
DIRECTORY = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def run():
    os.chdir(DIRECTORY)
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print("=" * 60)
        print(f"🚀 Plan4U Frontend UI is running at: http://localhost:{PORT}")
        print("   Dual-Panel Testing Portal:")
        print("   - Mode 1: Long Itinerary Plan (Panel 1 Master Planner)")
        print("   - Mode 2: Live In-Trip Copilot (Panel 2 Companion)")
        print("   Connecting to Backend API at: http://localhost:8000")
        print("=" * 60)
        print("Press Ctrl+C to stop the server.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down frontend server.")


if __name__ == "__main__":
    run()
