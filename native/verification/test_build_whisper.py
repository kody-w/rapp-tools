import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "packaging/build_whisper.py"
SPEC = importlib.util.spec_from_file_location("build_whisper", SCRIPT)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class BuildWhisperTests(unittest.TestCase):
    def archive(self, directory, entries):
        output = Path(directory) / "fixture.tar.gz"
        with tarfile.open(output, "w:gz") as target:
            for name, content in entries:
                info = tarfile.TarInfo(name)
                info.size = len(content)
                target.addfile(info, io.BytesIO(content))
        return output

    def test_extracts_one_verified_source_root(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.archive(directory, [("source/LICENSE", b"fixture license")])
            output = Path(directory) / "extracted"
            root = builder.extract_verified(archive, output)
            self.assertEqual(root, output / "source")
            self.assertEqual((root / "LICENSE").read_bytes(), b"fixture license")

    def test_rejects_archive_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.archive(directory, [("../escape", b"not allowed")])
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                builder.extract_verified(archive, Path(directory) / "extracted")
            self.assertFalse((Path(directory) / "escape").exists())

    def test_rejects_multiple_source_roots(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.archive(directory, [("one/a", b"a"), ("two/b", b"b")])
            with self.assertRaisesRegex(ValueError, "exactly one"):
                builder.extract_verified(archive, Path(directory) / "extracted")

    def test_rejects_symbolic_links(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "fixture.tar.gz"
            with tarfile.open(archive, "w:gz") as target:
                link = tarfile.TarInfo("source/linked")
                link.type = tarfile.SYMTYPE
                link.linkname = "/outside"
                target.addfile(link)
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                builder.extract_verified(archive, Path(directory) / "extracted")

    def test_limits_total_extracted_size(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = self.archive(directory, [("source/file", b"too large")])
            with patch.object(builder, "EXTRACTED_LIMIT", 3):
                with self.assertRaisesRegex(ValueError, "size limit"):
                    builder.extract_verified(archive, Path(directory) / "extracted")

    def test_accepts_only_system_runtime_libraries(self):
        results = [
            "arm64\n",
            "/tmp/whisper-cli:\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n",
        ]
        with patch.object(builder.subprocess, "check_output", side_effect=results):
            self.assertEqual(
                builder.inspect_binary(Path("/tmp/whisper-cli"), "arm64"),
                ["/usr/lib/libSystem.B.dylib"],
            )

    def test_rejects_homebrew_runtime_dependency(self):
        results = [
            "arm64\n",
            "/tmp/whisper-cli:\n\t/opt/homebrew/lib/libggml.dylib (compatibility version 1.0.0)\n",
        ]
        with patch.object(builder.subprocess, "check_output", side_effect=results):
            with self.assertRaisesRegex(ValueError, "non-system"):
                builder.inspect_binary(Path("/tmp/whisper-cli"), "arm64")

    def test_rejects_wrong_architecture(self):
        with patch.object(builder.subprocess, "check_output", return_value="arm64\n"):
            with self.assertRaisesRegex(ValueError, "architecture mismatch"):
                builder.inspect_binary(Path("/tmp/whisper-cli"), "x86_64")


if __name__ == "__main__":
    unittest.main()
