import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile


PACKAGING = Path(__file__).resolve().parents[1] / "packaging"
sys.path.insert(0, str(PACKAGING))
SPEC = importlib.util.spec_from_file_location("make_desktop_evidence", PACKAGING / "make_desktop_evidence.py")
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


class DesktopEvidenceTests(unittest.TestCase):
    def archive(self, root, entries):
        archive = Path(root) / "app.zip"
        with zipfile.ZipFile(archive, "w") as output:
            for name, data in entries:
                output.writestr(name, data)
        return archive

    def test_accepts_application_and_resource_forks(self):
        with tempfile.TemporaryDirectory() as root:
            archive = self.archive(root, [
                ("App.app/Contents/Info.plist", "fixture"),
                ("__MACOSX/App.app/Contents/._Info.plist", "fixture metadata"),
            ])
            evidence.check_zip_paths(archive, "App.app")

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as root:
            archive = self.archive(root, [("App.app/../../outside", "no")])
            with self.assertRaisesRegex(evidence.release_app.ReleaseError, "unsafe path"):
                evidence.check_zip_paths(archive, "App.app")

    def test_rejects_unrelated_top_level_payload(self):
        with tempfile.TemporaryDirectory() as root:
            archive = self.archive(root, [("unexpected.sh", "no")])
            with self.assertRaisesRegex(evidence.release_app.ReleaseError, "top-level"):
                evidence.check_zip_paths(archive, "App.app")

    def test_preserves_internal_framework_symlinks_but_rejects_escape(self):
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root) / "app.zip"
            link = zipfile.ZipInfo("App.app/Contents/Frameworks/Core.framework/Versions/Current")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr(link, "A")
            evidence.check_zip_paths(archive, "App.app")
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr(link, "../../../../../../outside")
            with self.assertRaisesRegex(evidence.release_app.ReleaseError, "symlink escapes"):
                evidence.check_zip_paths(archive, "App.app")

    def workflow(self, **overrides):
        return {
            "status": "completed", "conclusion": "success", "head_sha": "a" * 40,
            "repository": {"full_name": "kody-w/rapp-voice"}, **overrides,
        }

    def test_requires_same_repository_and_successful_source_commit_run(self):
        url = "https://github.com/kody-w/rapp-voice/actions/runs/123"
        body = io.BytesIO(json.dumps(self.workflow()).encode())
        with patch.object(evidence.urllib.request, "urlopen", return_value=body):
            evidence.verify_workflow(url, "kody-w/rapp-voice", "a" * 40)
        body = io.BytesIO(json.dumps(self.workflow(head_sha="b" * 40)).encode())
        with patch.object(evidence.urllib.request, "urlopen", return_value=body):
            with self.assertRaisesRegex(evidence.release_app.ReleaseError, "this source commit"):
                evidence.verify_workflow(url, "kody-w/rapp-voice", "a" * 40)
        with self.assertRaisesRegex(evidence.release_app.ReleaseError, "must belong"):
            evidence.verify_workflow(url, "other/repo", "a" * 40)


if __name__ == "__main__":
    unittest.main()
