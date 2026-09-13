import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("workspace_refresh", ROOT / "rapp_workspace.py")
refresh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refresh)
BUNDLES = ROOT / "workspace/artifacts"


class WorkspaceRefreshTests(unittest.TestCase):
    def protocol(self, directory):
        source = refresh.unpack_bundle(
            (BUNDLES / "authority.zip").read_bytes(), "authority", Path(directory)
        )
        spec = importlib.util.spec_from_file_location("fixture_rapp_reference", source / "rapp.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def project(self, directory):
        root = Path(directory) / "application"
        root.mkdir()
        (root / "README.md").write_text("# Existing application\n")
        (root / "settings.json").write_text('{"unchanged":true}\n')
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        return root

    def test_audit_does_not_execute_application_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            (root / "application.py").write_text("raise RuntimeError('must never execute')\n")
            before = refresh.inventory(root)
            result = refresh.audit(root)
            self.assertEqual(result["coverage"]["file_count"], 3)
            self.assertEqual(before["tree_sha256"], refresh.inventory(root)["tree_sha256"])
            self.assertFalse(result["freshness"]["checked"])
            self.assertEqual(result["rapp1"]["authenticated_acceptance"], "not-asserted")

    def test_duplicate_json_is_not_silently_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            (root / "bad.json").write_text('{"value":1,"value":2}')
            result = refresh.audit(root)
            self.assertTrue(any(item["code"] == "duplicate-json-key" for item in result["findings"]))

    def test_legacy_protocol_artifact_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            (root / "old.json").write_text('{"schema":"brainstem-egg/2.2-rapplication"}')
            result = refresh.audit(root)
            self.assertTrue(any(item["code"] == "retired-protocol-artifact" for item in result["findings"]))
            self.assertEqual(result["rapp1"]["verdict"], "nonconformant-artifacts-found")

    def test_bootstrap_plan_has_no_filesystem_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            before = refresh.inventory(root)
            result = refresh.bootstrap(root, owner="example", world_id="test-world")
            self.assertFalse(result["applied"])
            self.assertFalse((root / ".rapp").exists())
            self.assertEqual(before["tree_sha256"], refresh.inventory(root)["tree_sha256"])

    def test_bootstrap_uses_canonical_local_workspace_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            original = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
            with patch.object(refresh, "fetch_bytes", side_effect=AssertionError("network not authorized")):
                first = refresh.bootstrap(
                    root, apply=True, owner="example", world_id="test-world", bundle_dir=BUNDLES
                )
                workspace = Path(first["workspace_root"])
                (workspace / "owner-note.txt").write_text("Keep this private note.\n")
                second = refresh.bootstrap(
                    root, apply=True, owner="example", world_id="test-world", bundle_dir=BUNDLES
                )
            self.assertTrue(first["applied"])
            self.assertTrue(first["original_source_unchanged"])
            self.assertTrue(second["idempotent"])
            self.assertEqual(first["workspace"]["rappid"], second["workspace"]["rappid"])
            self.assertEqual((workspace / "owner-note.txt").read_text(), "Keep this private note.\n")
            self.assertEqual({name: (root / name).read_bytes() for name in original}, original)
            self.assertTrue((workspace / ".github/skills/rapp-workspace/SKILL.md").is_file())
            self.assertTrue((workspace / ".github/skills/rapp-private-hive/SKILL.md").is_file())
            self.assertTrue((workspace / "SPEC.md").is_file())
            registry = json.loads((workspace / "registry.json").read_text())
            self.assertEqual(len(registry["workspaces"]), 1)
            self.assertEqual(registry["workspaces"][0]["path"], str(root.resolve()))
            tracked = subprocess.check_output(
                ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"], text=True
            )
            self.assertNotIn(".rapp/workspace", tracked)
            self.assertNotIn(".rapp/cache", tracked)

    def test_world_change_is_refused_without_reminting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            first = refresh.bootstrap(
                root, apply=True, owner="example", world_id="one-world", bundle_dir=BUNDLES
            )
            identity = Path(first["workspace_root"]) / "rappid.json"
            before = identity.read_bytes()
            with self.assertRaisesRegex(refresh.WorkspaceError, "owner or world"):
                refresh.bootstrap(
                    root, apply=True, owner="example", world_id="another-world", bundle_dir=BUNDLES
                )
            self.assertEqual(identity.read_bytes(), before)

    def test_existing_unmanaged_workspace_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            workspace = root / ".rapp/workspace"
            workspace.mkdir(parents=True)
            existing = workspace / "precious.txt"
            existing.write_text("Do not replace")
            with self.assertRaisesRegex(refresh.WorkspaceError, "already exists"):
                refresh.bootstrap(
                    root, apply=True, owner="example", world_id="world", bundle_dir=BUNDLES
                )
            self.assertEqual(existing.read_text(), "Do not replace")

    def test_symlinked_control_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            outside = Path(directory) / "outside"
            outside.mkdir()
            (root / ".rapp").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(refresh.WorkspaceError):
                refresh.bootstrap(
                    root, apply=True, owner="example", world_id="world", bundle_dir=BUNDLES
                )
            self.assertEqual(list(outside.iterdir()), [])

    def test_modified_tooling_bundle_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            bundles = Path(directory) / "bundles"
            bundles.mkdir()
            (bundles / "authority.zip").write_bytes(b"not the approved bundle")
            with self.assertRaisesRegex(refresh.WorkspaceError, "immutable source pin"):
                refresh.bootstrap(
                    root, apply=True, owner="example", world_id="world", bundle_dir=bundles
                )
            self.assertFalse((root / ".rapp/workspace").exists())

    def test_cached_code_drift_prevents_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            refresh.bootstrap(root, apply=True, owner="example", world_id="world", bundle_dir=BUNDLES)
            cached = root / ".rapp/cache" / ("authority-" + refresh.AUTHORITY["commit"]) / "rapp.py"
            cached.write_text("raise RuntimeError('never execute modified cache')\n")
            with self.assertRaisesRegex(refresh.WorkspaceError, "Cached tooling changed"):
                refresh.bootstrap(root, apply=True, owner="example", world_id="world", bundle_dir=BUNDLES)

    def test_bundle_artifacts_match_the_operator_pins(self):
        for pin in refresh.BUNDLES.values():
            data = (BUNDLES / pin["filename"]).read_bytes()
            self.assertEqual(len(data), pin["bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), pin["sha256"])

    def test_frame_integrity_uses_the_pinned_reference_without_claiming_trust(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            protocol = self.protocol(directory)
            identity = protocol.mint_rappid("example", "test")
            frame = protocol.build_frame(
                "body.pulse", identity, 0, "2026-09-13T00:00:00.000Z", {"value": 1}, None
            )
            (root / "frame.json").write_text(protocol.canonical(frame))
            result = refresh.audit(root, bundle_dir=BUNDLES, stream_bindings={"frame.json": identity})
            checked = result["protocol_checks"]["checks"][0]
            self.assertEqual(checked["status"], "integrity-verified")
            self.assertTrue(checked["stream_binding_verified"])
            self.assertIn("authenticated kind/family registry", checked["missing_evidence"])
            self.assertEqual(result["rapp1"]["authenticated_acceptance"], "not-asserted")

    def test_frame_tampering_and_wrong_stream_binding_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            protocol = self.protocol(directory)
            identity = protocol.mint_rappid("example", "test")
            frame = protocol.build_frame(
                "body.pulse", identity, 0, "2026-09-13T00:00:00.000Z", {"value": 1}, None
            )
            frame["payload"]["value"] = 2
            (root / "frame.json").write_text(protocol.canonical(frame))
            result = refresh.audit(root, bundle_dir=BUNDLES)
            self.assertEqual(result["protocol_checks"]["checks"][0]["step"], "2")
            self.assertEqual(result["rapp1"]["verdict"], "nonconformant-artifacts-found")
            frame["payload"]["value"] = 1
            (root / "frame.json").write_text(protocol.canonical(frame))
            result = refresh.audit(
                root, bundle_dir=BUNDLES,
                stream_bindings={"frame.json": protocol.mint_rappid("example", "different")},
            )
            self.assertEqual(result["protocol_checks"]["checks"][0]["step"], "1a")

    def test_exact_integer_profile_limit_is_not_a_false_full_jcs_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            protocol = self.protocol(directory)
            frame = protocol.build_frame(
                "body.pulse", protocol.mint_rappid("example", "test"), 0,
                "2026-09-13T00:00:00.000Z", {"value": 1}, None
            )
            frame["payload"] = {"ratio": 0.1}
            (root / "frame.json").write_text(json.dumps(frame))
            result = refresh.audit(root, bundle_dir=BUNDLES)
            self.assertEqual(result["protocol_checks"]["checks"][0]["status"], "unsupported-profile")
            self.assertNotEqual(result["rapp1"]["verdict"], "nonconformant-artifacts-found")

    def test_frame_order_does_not_depend_on_file_names_and_forks_refuse_both(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            protocol = self.protocol(directory)
            identity = protocol.mint_rappid("example", "test")
            genesis = protocol.build_frame(
                "body.pulse", identity, 0, "2026-09-13T00:00:00.000Z", {"value": 0}, None
            )
            child = protocol.build_frame(
                "body.pulse", identity, 1, "2026-09-13T00:00:01.000Z",
                {"value": 1}, genesis["payload_hash"]
            )
            (root / "z-genesis.json").write_text(protocol.canonical(genesis))
            (root / "a-child.json").write_text(protocol.canonical(child))
            result = refresh.audit(root, bundle_dir=BUNDLES)
            self.assertTrue(all(x["status"] == "integrity-verified" for x in result["protocol_checks"]["checks"]))
            fork = protocol.build_frame(
                "body.pulse", identity, 1, "2026-09-13T00:00:01.000Z",
                {"value": 2}, genesis["payload_hash"]
            )
            (root / "b-fork.json").write_text(protocol.canonical(fork))
            result = refresh.audit(root, bundle_dir=BUNDLES)
            failed = [x for x in result["protocol_checks"]["checks"] if x["status"] == "invalid"]
            self.assertEqual(len(failed), 2)
            self.assertTrue(all("fork" in x["message"] for x in failed))

    def test_verify_refuses_changed_managed_workspace_capability(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            result = refresh.bootstrap(root, apply=True, owner="example", world_id="world", bundle_dir=BUNDLES)
            (Path(result["workspace_root"]) / "tools/workspace_manager.py").write_text("# changed\n")
            with self.assertRaisesRegex(refresh.WorkspaceError, "capability changed"):
                refresh.verify_workspace(root.resolve())

    def test_unexpected_cache_code_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            refresh.bootstrap(root, apply=True, owner="example", world_id="world", bundle_dir=BUNDLES)
            cache = root / ".rapp/cache" / ("authority-" + refresh.AUTHORITY["commit"])
            (cache / "unexpected.py").write_text("# not in the source bundle\n")
            with self.assertRaisesRegex(refresh.WorkspaceError, "unexpected files"):
                refresh.verify_workspace(root.resolve())

    def test_boolean_strings_cannot_authorize_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            result = json.loads(refresh.RappWorkspaceRefreshAgent().perform(
                operation="bootstrap", root=str(root), owner="example", world_id="world", apply="false"
            ))
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"]["code"], "invalid-boolean")
            self.assertFalse((root / ".rapp").exists())

    def test_non_git_private_state_is_excluded_and_digest_is_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "plain"
            root.mkdir()
            (root / "app.txt").write_text("public source")
            for name in refresh.PRIVATE_CONTROL_DIRS:
                target = root / name
                target.mkdir(parents=True, exist_ok=True)
                (target / "private.txt").write_text("do not inventory")
            snapshot = refresh.audit(root)["coverage"]
            self.assertEqual([x["path"] for x in snapshot["files"]], ["app.txt"])
            data = json.dumps(snapshot["files"], sort_keys=True, separators=(",", ":")).encode()
            self.assertEqual(snapshot["tree_sha256"], hashlib.sha256(data).hexdigest())

    def test_recursive_archive_artifacts_are_verified_without_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            protocol = self.protocol(directory)
            identity = protocol.mint_rappid("example", "test")
            frame = protocol.build_frame(
                "body.pulse", identity, 0, "2026-09-13T00:00:00.000Z", {"value": 1}, None
            )
            inner = io.BytesIO()
            with zipfile.ZipFile(inner, "w") as archive:
                archive.writestr("frame.json", protocol.canonical(frame))
            with zipfile.ZipFile(root / "outer.zip", "w") as archive:
                archive.writestr("inner.zip", inner.getvalue())
            result = refresh.audit(root, bundle_dir=BUNDLES)
            checks = result["protocol_checks"]["checks"]
            self.assertEqual(len(checks), 1)
            self.assertEqual(checks[0]["path"], "outer.zip!/inner.zip!/frame.json")
            self.assertEqual(checks[0]["status"], "integrity-verified")
            self.assertFalse((root / "inner.zip").exists())

    def test_archive_symlinks_are_explicitly_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            with zipfile.ZipFile(root / "links.zip", "w") as archive:
                info = zipfile.ZipInfo("outside")
                info.create_system = 3
                info.external_attr = 0o120777 << 16
                archive.writestr(info, "../../outside")
            result = refresh.audit(root)
            self.assertFalse(result["archives"][0]["complete"])
            self.assertTrue(any(x["code"] == "archive-review-incomplete" for x in result["findings"]))

    def test_archive_recursion_has_a_shared_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            data = b"{}"
            for depth in range(8):
                output = io.BytesIO()
                with zipfile.ZipFile(output, "w") as archive:
                    archive.writestr("nested.zip" if depth else "data.json", data)
                data = output.getvalue()
            (root / "deep.zip").write_bytes(data)
            result = refresh.audit(root)
            self.assertTrue(any(x["code"] == "archive-review-failed" and "depth" in x["message"]
                                for x in result["findings"]))

    def test_verify_cannot_pass_known_invalid_active_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            refresh.bootstrap(root, apply=True, owner="example", world_id="world", bundle_dir=BUNDLES)
            (root / "invalid.json").write_text('{"spec":"rapp/1","seq":0}')
            result = json.loads(refresh.RappWorkspaceRefreshAgent().perform(
                operation="verify", root=str(root), bundle_dir=str(BUNDLES)
            ))
            self.assertFalse(result["ok"])
            self.assertEqual(result["verification"]["status"], "blocked")

    def test_existing_root_workspace_reuses_identity_and_never_executes_its_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            protocol = self.protocol(directory)
            identity = {"schema": "rapp/1", "kind": "workspace", "mode": "solo",
                        "world_id": "world", "rappid": protocol.mint_rappid("example", "existing")}
            (root / "rappid.json").write_text(json.dumps(identity))
            for name in ["HOME.md", "AGENTS.md"]:
                (root / name).write_text("Keep this existing workspace file.\n")
            (root / ".github/skills").mkdir(parents=True)
            (root / "rapp-projects").mkdir()
            before = refresh.inventory(root)
            result = refresh.bootstrap(
                root, apply=True, owner="example", world_id="world", bundle_dir=BUNDLES
            )
            self.assertTrue(result["idempotent"])
            self.assertEqual(result["workspace"]["rappid"], identity["rappid"])
            self.assertEqual(result["workspace_root"], str(root.resolve()))
            self.assertFalse((root / ".rapp").exists())
            self.assertEqual(before["tree_sha256"], refresh.inventory(root)["tree_sha256"])

    def test_existing_incomplete_workspace_never_mints_a_second_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            protocol = self.protocol(directory)
            identity = {"schema": "rapp/1", "kind": "workspace", "mode": "hive",
                        "world_id": "world", "rappid": protocol.mint_rappid("example", "existing")}
            (root / "rappid.json").write_text(json.dumps(identity))
            with self.assertRaisesRegex(refresh.WorkspaceError, "Preserve the existing identity"):
                refresh.bootstrap(root, apply=True, owner="example", world_id="world", bundle_dir=BUNDLES)
            self.assertFalse((root / ".rapp").exists())

    def test_bundles_rebuild_byte_identically(self):
        spec = importlib.util.spec_from_file_location("builder", ROOT / "tools/build_workspace_bundles.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as directory:
            for kind, pin in refresh.BUNDLES.items():
                original = (BUNDLES / pin["filename"]).read_bytes()
                with zipfile.ZipFile(io.BytesIO(original)) as archive:
                    files = {name: archive.read(name) for name in archive.namelist()
                             if name != "bundle-manifest.json"}
                rebuilt = builder.build_bundle(kind, pin["repository"], pin["commit"], files, Path(directory))
                self.assertEqual(rebuilt["sha256"], pin["sha256"])
                self.assertEqual((Path(directory) / pin["filename"]).read_bytes(), original)

    def test_prepare_is_additive_idempotent_and_keeps_existing_root_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            original = b"# Existing public machine interface\r\nKeep these URLs.\r\n"
            (root / "SKILL.md").write_bytes(original)
            plan = refresh.prepare(root)
            self.assertFalse(plan["applied"])
            self.assertFalse((root / ".rapp").exists())
            first = refresh.prepare(root, apply=True, source_commit="a" * 40)
            snapshot = refresh.inventory(root)
            refresh.prepare(root, apply=True, source_commit="a" * 40)
            self.assertEqual(snapshot["tree_sha256"], refresh.inventory(root)["tree_sha256"])
            self.assertEqual(first["root_skill_compatibility"], "SKILL.md")
            self.assertTrue((root / "SKILL.md").read_bytes().startswith(original))
            self.assertEqual(len([p for p in root.iterdir() if p.name.casefold() == "skill.md"]), 1)
            (root / "SKILL.md").write_bytes(b"New owner instructions.\n" + (root / "SKILL.md").read_bytes())
            refresh.prepare(root, apply=True, source_commit="a" * 40)
            self.assertTrue((root / "SKILL.md").read_bytes().startswith(b"New owner instructions.\n" + original))

    def test_prepare_refuses_modified_managed_code_and_preserves_user_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            refresh.prepare(root, apply=True)
            loader = root / ".rapp/bootstrap.py"
            loader.write_text("# user modification\n")
            with self.assertRaisesRegex(refresh.WorkspaceError, "modified capability"):
                refresh.prepare(root, apply=True)
            self.assertEqual(loader.read_text(), "# user modification\n")

    def test_prepared_loader_bootstraps_offline_and_verifies_warm_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            refresh.prepare(root, apply=True)
            before = refresh.inventory(root)
            command = [sys.executable, "-I", "-B", str(root / ".rapp/bootstrap.py")]
            cold = subprocess.run([
                *command, "bootstrap", "--apply", "--owner", "example", "--world-id", "world",
                "--operator-file", str(ROOT / "rapp_workspace.py"), "--bundle-dir", str(BUNDLES),
            ], capture_output=True, text=True)
            self.assertEqual(cold.returncode, 0, cold.stderr + cold.stdout)
            first = json.loads(cold.stdout)
            warm = subprocess.run([
                *command, "bootstrap", "--apply", "--owner", "example", "--world-id", "world",
            ], capture_output=True, text=True)
            self.assertEqual(warm.returncode, 0, warm.stderr + warm.stdout)
            self.assertEqual(json.loads(warm.stdout)["workspace"]["rappid"], first["workspace"]["rappid"])
            verified = subprocess.run([*command, "verify"], capture_output=True, text=True)
            self.assertEqual(verified.returncode, 0, verified.stderr + verified.stdout)
            self.assertEqual(before["tree_sha256"], refresh.inventory(root)["tree_sha256"])

    def test_prepared_loader_fails_closed_without_network_or_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            refresh.prepare(root, apply=True)
            command = [sys.executable, "-I", "-B", str(root / ".rapp/bootstrap.py"), "audit"]
            missing = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("no download was attempted", missing.stderr)
            changed = Path(directory) / "changed.py"
            changed.write_text("raise RuntimeError('never execute')\n")
            mismatch = subprocess.run([*command, "--operator-file", str(changed)],
                                      capture_output=True, text=True)
            self.assertNotEqual(mismatch.returncode, 0)
            self.assertIn("immutable pin", mismatch.stderr)
            self.assertFalse((root / ".rapp/cache").exists())

    def test_cli_stream_bindings_are_an_independent_failure_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.project(directory)
            protocol = self.protocol(directory)
            identity = protocol.mint_rappid("example", "one")
            frame = protocol.build_frame(
                "body.pulse", identity, 0, "2026-09-13T00:00:00.000Z", {}, None
            )
            (root / "frame.json").write_text(protocol.canonical(frame))
            binding = Path(directory) / "bindings.json"
            binding.write_text(json.dumps({"frame.json": protocol.mint_rappid("example", "two")}))
            result = subprocess.run([
                sys.executable, "-I", "-B", str(ROOT / "rapp_workspace.py"), "audit", str(root),
                "--bundle-dir", str(BUNDLES), "--stream-bindings", str(binding),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["protocol_checks"]["checks"][0]["step"], "1a")
            self.assertEqual(report["rapp1"]["verdict"], "nonconformant-artifacts-found")

    def test_portable_skill_carries_exact_source_and_the_complete_workflow(self):
        skill = ROOT / "skills/rapp-workspace-refresh"
        self.assertEqual((skill / "scripts/agent.py").read_bytes(), (ROOT / "rapp_workspace.py").read_bytes())
        text = (skill / "SKILL.md").read_text()
        self.assertIn(refresh.REFRESH_WORKFLOW, text)
        self.assertIn("agent-sha256: " + json.dumps(hashlib.sha256((ROOT / "rapp_workspace.py").read_bytes()).hexdigest()), text)
        self.assertTrue((skill / "LICENSE").is_file())


if __name__ == "__main__":
    unittest.main()
