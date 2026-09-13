import importlib.util
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "packaging/release_app.py"
SPEC = importlib.util.spec_from_file_location("release_app", SCRIPT)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class ReleaseAppTests(unittest.TestCase):
    def test_report_normalization_handles_macos_private_path_alias(self):
        app = Path("/var/folders/fixture/RAPPVoice.app")
        real = Path("/private/var/folders/fixture/RAPPVoice.app")
        report = f"Executable={real}/Contents/MacOS/RAPPVoice\n{app}: accepted\n"
        with patch.object(Path, "resolve", return_value=real):
            actual = release.portable_report(report, app)
        self.assertEqual(
            actual, "Executable=RAPPVoice.app/Contents/MacOS/RAPPVoice\nRAPPVoice.app: accepted\n"
        )
        self.assertNotIn("/privateRAPPVoice", actual)

    def test_report_normalization_preserves_unrelated_text(self):
        app = Path("/build/release/App.app")
        report = "source=Notarized Developer ID\nAuthority=Developer ID Application: Fixture\n"
        self.assertEqual(release.portable_report(report, app), report)

    def signature(self, authority="Developer ID Application: Fixture",
                  team="TEAM123456", runtime=True, timestamp=True):
        return "\n".join([
            f"Authority={authority}",
            f"TeamIdentifier={team}",
            "CodeDirectory v=20500 flags=0x10000(runtime)" if runtime else "CodeDirectory flags=0x0",
            "Timestamp=verified fixture timestamp" if timestamp else "",
            "CDHash=" + "a" * 40,
        ])

    def check_signature(self, detail, entitlements=None):
        completed = subprocess.CompletedProcess(
            [], 0, stdout=plistlib.dumps(entitlements or {}).decode(), stderr=""
        )
        with patch.object(release, "command", side_effect=["", detail]):
            with patch.object(release.subprocess, "run", return_value=completed):
                return release.signature_info(Path("/fixture/app"), "TEAM123456")

    def test_requires_developer_id_not_development_signing(self):
        with self.assertRaises(release.ReleaseError):
            self.check_signature(self.signature(authority="Apple Development: Fixture"))

    def test_requires_hardened_runtime(self):
        with self.assertRaises(release.ReleaseError):
            self.check_signature(self.signature(runtime=False))

    def test_requires_secure_timestamp(self):
        with self.assertRaises(release.ReleaseError):
            self.check_signature(self.signature(timestamp=False))

    def test_requires_the_selected_team(self):
        with self.assertRaises(release.ReleaseError):
            self.check_signature(self.signature(team="OTHER12345"))

    def test_rejects_debugging_entitlement(self):
        with self.assertRaises(release.ReleaseError):
            self.check_signature(
                self.signature(), {"com.apple.security.get-task-allow": True}
            )

    def test_reports_only_observed_signature_facts(self):
        result = self.check_signature(self.signature())
        self.assertTrue(result["developer_id"])
        self.assertTrue(result["hardened_runtime"])
        self.assertEqual(result["team_id"], "TEAM123456")
        self.assertFalse(result["get_task_allow"])

    def test_requires_a_clean_immutable_source_revision(self):
        with patch.object(release, "command", return_value=" M native/App.swift"):
            with self.assertRaisesRegex(release.ReleaseError, "uncommitted"):
                release.source_commit(Path("/fixture/repo"))
        with patch.object(release, "command", side_effect=["", "not-a-commit"]):
            with self.assertRaisesRegex(release.ReleaseError, "full Git commit"):
                release.source_commit(Path("/fixture/repo"))

    def test_rejects_ambiguous_application_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(release.ReleaseError):
                release.only_app(root)
            (root / "First.app").mkdir()
            self.assertEqual(release.only_app(root), root / "First.app")
            (root / "Second.app").mkdir()
            with self.assertRaises(release.ReleaseError):
                release.only_app(root)


if __name__ == "__main__":
    unittest.main()
