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
        self.base = "https://cdn.example.com/blog/static/"
        (self.dist / "assets").mkdir()
        (self.dist / "assets/app.js").write_text("export const ready = true")
        (self.dist / "assets/app.css").write_text("body {color: black}")
        (self.dist / "index.html").write_text(
            f'<script type="module" src="{self.base}assets/app.js"></script>'
            f'<link rel="stylesheet" href="{self.base}assets/app.css">'
        )
        spec = importlib.util.spec_from_file_location("publish_static_assets_test_module", SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)

    def plan(self, **overrides):
        arguments = dict(
            directory=self.dist,
            cdn_base_url="https://cdn.example.com/blog", static_prefix="static",
        )
        arguments.update(overrides)
        return self.module.plan_assets(**arguments)

    def test_plan_keeps_html_at_origin_and_maps_fixed_cdn_paths_to_oss_keys(self):
        assets = self.plan()
        self.assertEqual([asset.key for asset in assets], [
            "static/assets/app.css", "static/assets/app.js",
        ])
        self.assertEqual([asset.content_type for asset in assets], ["text/css", "text/javascript"])
        self.assertEqual([asset.path.name for asset in assets], ["app.css", "app.js"])

    def test_plan_refuses_origin_builds_wrong_domains_and_nonmatching_directories(self):
        for base in ("", "/", "https://other.example.com/static/",
                     self.base + "release-1/", "https://cdn.example.com/blog/static-other/",
                     self.base + "?token=secret"):
            (self.dist / "index.html").write_text(f'<script type="module" src="{base}assets/app.js"></script>')
            with self.subTest(base=base), self.assertRaises(ValueError):
                self.plan()
        (self.dist / "index.html").write_text('<script type="module" src="/assets/app.js"></script>')
        with self.assertRaises(ValueError):
            self.plan()

    def test_custom_prefix_is_used_for_both_build_validation_and_object_keys(self):
        (self.dist / "index.html").write_text(
            '<script type="module" src="https://cdn.example.com/blog/web/static/assets/app.js"></script>'
        )
        assets = self.plan(cdn_base_url="https://cdn.example.com/blog/", static_prefix="/web/static/")
        self.assertEqual([asset.key for asset in assets], [
            "web/static/assets/app.css", "web/static/assets/app.js",
        ])

    def test_invalid_cdn_or_static_prefix_is_rejected(self):
        for cdn in ("", "http://cdn.example.com", "https://user:secret@cdn.example.com",
                    "https://cdn.example.com/?token=secret", "https://cdn.example.com/#fragment"):
            with self.subTest(cdn=cdn), self.assertRaises(ValueError):
                self.plan(cdn_base_url=cdn)
        for prefix in ("", "../static", "static//assets", "static?token=secret"):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                self.plan(static_prefix=prefix)

    def test_missing_entry_assets_and_traversal_are_rejected_before_publishing(self):
        for suffix in ("assets/missing.js", "../app.js", "%2e%2e/app.js", "assets/app.js?token=1"):
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
        (self.dist / "assets/link.js").symlink_to(self.dist / "assets/app.js")
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
                self.wfile.write(b"<PostResponse><Key>static/assets/app.css</Key></PostResponse>")

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
                       "Cache-Control": "public,max-age=0,s-maxage=31536000,must-revalidate"},
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
