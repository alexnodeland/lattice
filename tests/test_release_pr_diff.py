"""CI's check of release-please's pull requests (scripts/release_pr_diff.py): only versions and
changelogs pass."""

import release_pr_diff as rpd

RELEASE = """\
diff --git a/.release-please-manifest.json b/.release-please-manifest.json
--- a/.release-please-manifest.json
+++ b/.release-please-manifest.json
@@ -4,3 +4,3 @@
   "packages/grantr": "0.1.0",
-  "packages/relayr": "0.1.1",
+  "packages/relayr": "0.2.0",
   "packages/portalr": "0.3.0",
diff --git a/packages/relayr/CHANGELOG.md b/packages/relayr/CHANGELOG.md
--- a/packages/relayr/CHANGELOG.md
+++ b/packages/relayr/CHANGELOG.md
@@ -5,0 +6,2 @@
+## [0.2.0](https://example.invalid) (2026-10-29)
+* anything at all
diff --git a/packages/relayr/pyproject.toml b/packages/relayr/pyproject.toml
--- a/packages/relayr/pyproject.toml
+++ b/packages/relayr/pyproject.toml
@@ -2,3 +2,3 @@
 name = "relayr-ai"
-version = "0.1.1"
+version = "0.2.0"
 description = "relayr"
diff --git a/uv.lock b/uv.lock
--- a/uv.lock
+++ b/uv.lock
@@ -4389,3 +4389,3 @@
 name = "relayr-ai"
-version = "0.1.1"
+version = "0.2.0"
 source = { editable = "packages/relayr" }
"""


def test_a_release_passes() -> None:
    assert list(rpd.problems(RELEASE)) == []


def test_another_file_fails() -> None:
    diff = RELEASE + "diff --git a/scripts/x.py b/scripts/x.py\n+print()\n"
    assert list(rpd.problems(diff)) == ["scripts/x.py: not a file a release changes"]


def test_a_line_but_a_version_fails() -> None:
    diff = RELEASE.replace(
        '+version = "0.2.0"\n description', '+version = "0.2.0"\n+x = 1\n description'
    )
    assert list(rpd.problems(diff)) == ["packages/relayr/pyproject.toml: not a version: +x = 1"]


def test_a_dependencys_version_in_uv_lock_fails() -> None:
    diff = RELEASE.replace(
        'editable = "packages/relayr" }', 'registry = "https://pypi.org/simple" }'
    )
    assert len(list(rpd.problems(diff))) == 1
