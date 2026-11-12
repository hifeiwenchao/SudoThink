"""Static publishing boundaries; no cloud account or developer credentials are used."""
import importlib.util
import json
import os
import sys
import tempfile
import threading
import unittest
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish_static_assets.py"


class StaticAssetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.dist = Path(self.directory.name)
        self.base = "https://cdn.example.com/blog/static/release-1/"
        (self.dist / "assets").mkdir()
        (self.dist / "assets/app-123.js").write_text("export const ready = true")
        (self.dist / "assets/app-123.css").write_text("body {color: black}")
        (self.dist / "index.html").write_text(
            f'<script type="module" src="{self.base}assets/app-123.js"></script>'
            f'<link rel="stylesheet" href="{self.base}assets/app-123.css">'
        )
        spec = importlib.util.spec_from_file_location("publish_static_assets_test_module", SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)

    def plan(self, **overrides):
        arguments = dict(
            directory=self.dist, asset_base_url=self.base,
            cdn_base_url="https://cdn.example.com/blog", static_prefix="static",
        )
        arguments.update(overrides)
        return self.module.plan_assets(**arguments)

    def test_plan_keeps_html_at_origin_and_maps_versioned_cdn_paths_to_oss_keys(self):
        assets = self.plan()
        self.assertEqual([asset.key for asset in assets], [
            "static/release-1/assets/app-123.css", "static/release-1/assets/app-123.js",
        ])
        self.assertEqual([asset.content_type for asset in assets], ["text/css", "text/javascript"])
        self.assertEqual([asset.path.name for asset in assets], ["app-123.css", "app-123.js"])

    def test_plan_refuses_origin_builds_wrong_domains_and_unversioned_prefixes(self):
        for base in ("", "/", "https://other.example.com/static/release-1/",
                     "https://cdn.example.com/blog/static/", self.base + "?token=secret"):
            with self.subTest(base=base), self.assertRaises(ValueError):
                self.plan(asset_base_url=base)
        (self.dist / "index.html").write_text('<script type="module" src="/assets/app-123.js"></script>')
        with self.assertRaises(ValueError):
            self.plan()

    def test_missing_entry_assets_and_traversal_are_rejected_before_publishing(self):
        for suffix in ("assets/missing.js", "../app.js", "%2e%2e/app.js", "assets/app-123.js?token=1"):
            (self.dist / "index.html").write_text(f'<script type="module" src="{self.base}{suffix}"></script>')
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                self.plan()

    def test_symlinks_unknown_files_and_secret_files_are_not_published(self):
        for filename in (".env", "build.map", "secrets.pem"):
            file = self.dist / filename
            file.write_text("private-data")
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                self.plan()
            file.unlink()
        (self.dist / "assets/link.js").symlink_to(self.dist / "assets/app-123.js")
        with self.assertRaises(ValueError):
            self.plan()

    def test_static_upload_uses_multipart_file_last_and_accepts_oss_xml_response(self):
        captured = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                captured["headers"] = dict(self.headers)
                captured["body"] = self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(201)
                self.end_headers()
                self.wfile.write(b"<PostResponse><Key>static/release-1/assets/app-123.css</Key></PostResponse>")

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        asset = self.plan()[0]
        form = {
            "upload_url": f"http://127.0.0.1:{server.server_port}/",
            "fields": {"key": asset.key, "policy": "signed-policy", "Content-Type": "text/css",
                       "Cache-Control": "public,max-age=31536000,immutable"},
        }
        self.module.post_asset(asset, form)
        self.assertNotIn("Authorization", captured["headers"])
        message = BytesParser(policy=policy.default).parsebytes(
            ("Content-Type: " + captured["headers"]["Content-Type"] + "\r\n\r\n").encode()
            + captured["body"]
        )
        parts = list(message.iter_parts())
        self.assertEqual([part.get_param("name", header="Content-Disposition") for part in parts],
                         ["key", "policy", "Content-Type", "Cache-Control", "file"])
        self.assertEqual(parts[-1].get_content_type(), "text/css")
        self.assertEqual(parts[-1].get_payload(decode=True), asset.path.read_bytes())


if __name__ == "__main__":
    unittest.main()
