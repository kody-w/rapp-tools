import json
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]


class NativeCatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / "catalog/catalog.json").read_text())

    def test_exactly_four_existing_applications(self):
        self.assertEqual(self.catalog["count"], 4)
        self.assertEqual(
            {item["id"] for item in self.catalog["tools"]},
            {"rapp_voice", "rapp_rewind", "rapp_shot", "rapp_crispy"},
        )

    def test_native_downloads_have_versioned_same_repository_urls(self):
        versions = {"rapp_voice": "1.1.1", "rapp_rewind": "1.2.1",
                    "rapp_shot": "1.3.1", "rapp_crispy": "1.5.1"}
        for tool in self.catalog["tools"]:
            native = tool["native_release"]
            version = versions[tool["id"]]
            self.assertEqual(native["version"], version)
            self.assertEqual(native["minimum_macos"], "14.0")
            self.assertRegex(native["source_commit"], r"^[a-f0-9]{40}$")
            self.assertEqual(
                native["release_url"],
                f"https://github.com/kody-w/{tool['repo']}/releases/tag/v{version}",
            )
            self.assertEqual(set(native["downloads"]), {"arm64", "x86_64"})
            for arch, url in native["downloads"].items():
                self.assertEqual(
                    url,
                    f"https://github.com/kody-w/{tool['repo']}/releases/download/"
                    f"v{version}/{tool['id']}-{version}-{arch}.zip",
                )
            self.assertTrue(native["setup"].strip())

    def test_legacy_metadata_is_not_mislabeled_as_native(self):
        legacy = {"rapp_voice": "1.0.0", "rapp_rewind": "1.1.0",
                  "rapp_shot": "1.2.0", "rapp_crispy": "1.4.0"}
        for tool in self.catalog["tools"]:
            self.assertEqual(tool["version"], legacy[tool["id"]])
            self.assertEqual(tool["runtime"], "twin")
            self.assertRegex(tool["egg_sha256"], r"^[a-f0-9]{64}$")
        page = (ROOT / "index.html").read_text()
        self.assertIn("Historical CLI/twin compatibility metadata", page)
        self.assertIn('id="native-grid"', page)
        self.assertIn("not a fifth app", page)

    def test_page_rejects_invalid_download_references(self):
        page = (ROOT / "index.html").read_text()
        script = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
        script = re.sub(r"showNativeReleases\(\);\s*$", "", script)
        program = script + "\nconst tools = " + json.dumps(self.catalog["tools"]) + """
for (const tool of tools) checkedRelease(tool);
const bad = JSON.parse(JSON.stringify(tools[0]));
bad.native_release.downloads.arm64 = "javascript:alert(1)";
let rejected = false;
try { checkedRelease(bad); } catch (_) { rejected = true; }
if (!rejected) throw new Error("Unsafe native download was accepted");
const stale = JSON.parse(JSON.stringify(tools[0]));
stale.native_release.version = "0.0.1";
rejected = false;
try { checkedRelease(stale); } catch (_) { rejected = true; }
if (!rejected) throw new Error("Mismatched release version was accepted");
"""
        subprocess.run(["node", "-e", program], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
