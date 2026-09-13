import argparse
import hashlib
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("legacy_rapptools", str(ROOT / "rapptools"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
tools = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(tools)
TOOL = {"id": "rapp_shot", "agent": "RappShot", "port": 7093, "actions": ["doctor"]}


class LegacyToolsTests(unittest.TestCase):
    def test_missing_archive_hash_never_authorizes_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            egg = Path(directory) / "fixture.egg"
            egg.write_bytes(b"fixture")
            self.assertFalse(tools.verify_egg(TOOL, egg, "fixture"))
            pinned = {**TOOL, "egg_sha256": hashlib.sha256(b"fixture").hexdigest()}
            self.assertTrue(tools.verify_egg(pinned, egg, "fixture"))

    def test_unowned_listener_is_never_signalled(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(tools, "ROOT", directory):
            with patch.object(tools, "http_ok", return_value=True), patch.object(tools.os, "kill") as kill:
                with self.assertRaisesRegex(ValueError, "unowned service"):
                    tools.stop_owned(TOOL)
                kill.assert_not_called()

    def test_reused_pid_is_never_signalled(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(tools, "ROOT", directory):
            tools.process_record(TOOL).write_text(json.dumps(
                {"tool": TOOL["id"], "pid": 24680, "identity": "original process"}
            ))
            with patch.object(tools, "process_identity", return_value="unrelated reused PID"):
                with patch.object(tools.os, "kill") as kill:
                    with self.assertRaisesRegex(ValueError, "reused"):
                        tools.stop_owned(TOOL)
                    kill.assert_not_called()

    def test_only_recorded_matching_process_can_be_stopped(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(tools, "ROOT", directory):
            receipt = tools.process_record(TOOL)
            receipt.write_text(json.dumps({"tool": TOOL["id"], "pid": 24680, "identity": "owned"}))
            with patch.object(tools, "process_identity", side_effect=["owned", None]):
                with patch.object(tools, "http_ok", return_value=False), patch.object(tools.os, "kill") as kill:
                    self.assertEqual(tools.stop_owned(TOOL), 24680)
                    kill.assert_called_once_with(24680, tools.signal.SIGTERM)
                    self.assertFalse(receipt.exists())

    def test_archive_paths_and_symlinks_are_refused_without_extraction(self):
        for name, mode in [("../escape", 0o100644), ("absolute", 0o120777)]:
            data = io.BytesIO()
            with zipfile.ZipFile(data, "w") as archive:
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = mode << 16
                archive.writestr(info, b"fixture")
            data.seek(0)
            with self.assertRaises(ValueError):
                tools.validate_legacy_archive(data)

    def test_action_override_is_rejected_before_network(self):
        args = argparse.Namespace(id="rapp_shot", action="doctor", arg=["action=delete"], timeout=1)
        with patch.object(tools, "tool", return_value=TOOL), patch.object(tools, "http_ok") as network:
            self.assertEqual(tools.cmd_call(args), 2)
            network.assert_not_called()

    def test_empty_host_response_is_not_success(self):
        args = argparse.Namespace(id="rapp_shot", action="doctor", arg=[], timeout=1)
        with patch.object(tools, "tool", return_value=TOOL), patch.object(tools, "http_ok", return_value=True):
            with patch.object(tools, "chat", return_value={}):
                self.assertEqual(tools.cmd_call(args), 1)

    def test_fleet_does_not_hide_failed_hatches(self):
        args = argparse.Namespace(force=False, source="repo")
        with patch.object(tools, "catalog", return_value={"tools": [TOOL]}):
            with patch.object(tools, "cmd_hatch", return_value=1), patch.object(tools, "cmd_status", return_value=0):
                self.assertEqual(tools.cmd_hatch_all(args), 1)

    def test_retired_rebuild_cannot_overwrite_published_archives(self):
        result = subprocess.run(["bash", str(ROOT / "tools/rebuild-eggs.sh")],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("immutable", result.stderr)

    def test_historical_packer_refuses_replacing_different_archive_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "data.txt").write_text("fixture")
            target = root / "retained.egg"
            target.write_bytes(b"immutable old archive")
            result = subprocess.run(
                ["python3", str(ROOT / "tools/packegg.py"), str(source), str(target)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(target.read_bytes(), b"immutable old archive")


if __name__ == "__main__":
    unittest.main()
