import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "build_release.py"
SPEC = importlib.util.spec_from_file_location("build_release", SCRIPT)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.fixture = tempfile.TemporaryDirectory()
        self.addCleanup(self.fixture.cleanup)
        self.fixture_root = Path(self.fixture.name)
        self.license_text = (release.ROOT / "LICENSE").read_bytes()
        metadata = json.loads((release.ROOT / "publishing/marketplace.json").read_text())
        metadata["author"] = None
        (self.fixture_root / "publishing").mkdir()
        (self.fixture_root / "publishing/marketplace.json").write_text(json.dumps(metadata))
        (self.fixture_root / "NOTICE.md").write_text("Test-only build notice.\n")
        fixture_skill = self.fixture_root / "dual-session-exec"
        shutil.copytree(release.SKILL, fixture_skill)
        (fixture_skill / "LICENSE").unlink(missing_ok=True)
        for key, value in [("ROOT", self.fixture_root), ("SKILL", fixture_skill)]:
            guard = patch.object(release, key, value)
            guard.start()
            self.addCleanup(guard.stop)

    def test_authorless_draft_does_not_invent_marketplace_author_and_hashes_match(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "draft"
            status = release.build(out)
            self.assertIsNone(status["author"])
            self.assertFalse(status["workbuddy_archive_created"])
            self.assertFalse(list(out.glob("*workbuddy.zip")))
            with zipfile.ZipFile(next(out.glob("*.zip"))) as package:
                self.assertIn("dual-session-exec/SKILL.md", package.namelist())
                for name in package.namelist():
                    self.assertTrue(name.startswith("dual-session-exec/"))
                    self.assertNotIn("..", Path(name).parts)
                    self.assertNotIn(".work", name)
                    self.assertNotIn("__pycache__", name)
                    data = package.read(name).decode("utf-8")
                    self.assertNotIn("/Users/", data)
                    self.assertNotIn("/root/", data)
            for line in (out / "SHA256SUMS").read_text().splitlines():
                digest, name = line.split("  ", 1)
                self.assertEqual(digest, hashlib.sha256((out / name).read_bytes()).hexdigest())
            with self.assertRaises(FileExistsError):
                release.build(out)

    def test_marketplace_variant_has_confirmed_author_and_identical_body_and_scripts(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "market"
            result = release.build(out, 'Test Author: "quoted"')
            self.assertTrue(result["workbuddy_archive_created"])
            self.assertTrue(result["market_metadata_complete"])
            self.assertFalse(result["submission_ready"])
            self.assertIn("license", result["pending"])
            self.assertIn("pricing", result["pending"])
            with zipfile.ZipFile(out / "dual-session-exec-1.0.0-workbuddy.zip") as market, \
                    zipfile.ZipFile(out / "dual-session-exec-1.0.0-portable.zip") as portable:
                front, body = market.read("dual-session-exec/SKILL.md").decode().split("---", 2)[1:]
                fields = {line.split(":", 1)[0]: json.loads(line.split(":", 1)[1])
                          for line in front.strip().splitlines()}
                self.assertEqual(fields["author"], 'Test Author: "quoted"')
                self.assertEqual(fields["name"], "dual-session-exec")
                self.assertEqual(len(fields["examples_zh"]), 3)
                self.assertEqual(body, portable.read("dual-session-exec/SKILL.md").decode().split("---", 2)[2])
                for name in market.namelist():
                    if not name.endswith("/SKILL.md"):
                        self.assertEqual(market.read(name), portable.read(name))

    def test_empty_author_is_not_treated_as_an_authorized_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "invalid"
            with self.assertRaises(ValueError):
                release.build(out, " ")
            self.assertFalse(out.exists())

    def test_explicit_market_draft_keeps_unknown_author_and_verified_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "market-draft"
            result = release.build(out, market_draft=True)
            self.assertTrue(result["workbuddy_archive_created"])
            self.assertEqual(result["workbuddy_archive_kind"], "draft")
            self.assertFalse(result["submission_ready"])
            self.assertFalse(result["review_submitted"])
            self.assertFalse(result["market_metadata_complete"])
            self.assertEqual(result["missing_market_metadata"], ["author"])
            self.assertIsNone(result["author"])
            self.assertIn("license", result["pending"])
            self.assertIn("pricing", result["pending"])
            self.assertFalse((out / "dual-session-exec-1.0.0-workbuddy.zip").exists())
            metadata = json.loads((out / "MARKET_METADATA.json").read_text())
            self.assertIsNone(metadata["author"])
            self.assertEqual(metadata["version"], "1.0.0")
            with zipfile.ZipFile(out / result["workbuddy_archive_file"]) as market, \
                    zipfile.ZipFile(out / "dual-session-exec-1.0.0-portable.zip") as portable:
                front, body = market.read("dual-session-exec/SKILL.md").decode().split("---", 2)[1:]
                fields = {line.split(":", 1)[0]: json.loads(line.split(":", 1)[1])
                          for line in front.strip().splitlines()}
                self.assertEqual(fields, metadata)
                self.assertEqual(body, portable.read("dual-session-exec/SKILL.md").decode().split("---", 2)[2])
                self.assertEqual(market.namelist(), portable.namelist())
                for name in market.namelist():
                    if not name.endswith("/SKILL.md"):
                        self.assertEqual(market.read(name), portable.read(name))

    def test_draft_mode_still_rejects_an_empty_explicit_author(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "invalid-draft"
            with self.assertRaises(ValueError):
                release.build(out, " ", market_draft=True)
            self.assertFalse(out.exists())

    def test_confirmed_mit_free_release_includes_license_without_publishing(self):
        author = "双会话工坊（Dual Session Workshop）"
        metadata_path = release.ROOT / "publishing/marketplace.json"
        metadata = json.loads(metadata_path.read_text())
        metadata["author"] = author
        metadata_path.write_text(json.dumps(metadata))
        (release.ROOT / "LICENSE").write_bytes(self.license_text)
        (release.SKILL / "LICENSE").write_bytes(self.license_text)
        (release.ROOT / "publishing/release-decisions.json").write_text(json.dumps({
            "license": "MIT", "pricing": {"mode": "free", "price": 0, "subscription": False}
        }))
        out = release.ROOT / "confirmed"
        status = release.build(out)
        self.assertEqual(status["author"], author)
        self.assertEqual(status["license"], "MIT")
        self.assertEqual(status["pricing"], "free")
        self.assertFalse(status["pricing_details"]["subscription"])
        self.assertTrue(status["user_decisions_confirmed"])
        self.assertEqual(status["pending"], ["target-release acceptance"])
        self.assertTrue(status["market_metadata_complete"])
        self.assertFalse(status["submission_ready"])
        self.assertFalse(status["review_submitted"])
        self.assertFalse(status["published"])
        self.assertFalse(status["platform_pricing_applied"])
        for name in ["dual-session-exec-1.0.0-workbuddy.zip", "dual-session-exec-1.0.0-portable.zip"]:
            with zipfile.ZipFile(out / name) as package:
                self.assertEqual(package.read("dual-session-exec/LICENSE"), self.license_text)
                self.assertEqual(len(package.namelist()), 13)
        self.assertEqual((out / "LICENSE").read_bytes(), self.license_text)

    def test_mit_decision_rejects_missing_or_mismatched_packaged_license(self):
        (release.ROOT / "publishing/release-decisions.json").write_text(json.dumps({"license": "MIT"}))
        out = release.ROOT / "invalid-mit"
        with self.assertRaises(ValueError):
            release.build(out)
        self.assertFalse(out.exists())
        (release.ROOT / "LICENSE").write_bytes(self.license_text)
        (release.SKILL / "LICENSE").write_text("Different license text\n")
        with self.assertRaises(ValueError):
            release.build(out)
        self.assertFalse(out.exists())
