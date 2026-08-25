from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from agent_lab.config import ValidationConfig
from agent_lab.validation import REQUIRED_CSP, material_change, validate_static


def csp_text() -> str:
    return "; ".join(
        f"{directive} {' '.join(sorted(values))}"
        for directive, values in REQUIRED_CSP.items()
    )


def page(body: str = "<h1>Hello</h1>", script: str = "") -> str:
    return (
        "<!doctype html><html><head>"
        '<meta charset="utf-8">'
        f'<meta http-equiv="Content-Security-Policy" content="{csp_text()}">'
        f"<style>body {{ color: white; }}</style><script>{script}</script>"
        f"</head><body>{body}</body></html>"
    )


CONFIG = ValidationConfig(
    max_site_bytes=1024 * 1024,
    max_file_bytes=512 * 1024,
    max_pages=10,
    browser_timeout_seconds=5,
    require_browser=True,
)


class ValidationTests(TestCase):
    def test_valid_single_file_site_accepts_inline_code(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(page(script="document.body.dataset.ready = 'yes'"))
            report = validate_static(root, CONFIG)
            self.assertTrue(report.ok, report.static_errors)

    def test_network_code_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(page(script="fetch('/collect')"))
            report = validate_static(root, CONFIG)
            self.assertFalse(report.ok)
            self.assertTrue(any("network request" in error for error in report.static_errors))

    def test_forms_are_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(page(body="<form><input></form>"))
            report = validate_static(root, CONFIG)
            self.assertFalse(report.ok)
            self.assertTrue(any("forbidden <form>" in error for error in report.static_errors))

    def test_broken_local_link_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(page(body='<a href="missing.html">Missing</a>'))
            report = validate_static(root, CONFIG)
            self.assertFalse(report.ok)
            self.assertTrue(any("broken local link" in error for error in report.static_errors))

    def test_whitespace_only_edit_is_not_material(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = root / "before"
            after = root / "after"
            before.mkdir()
            after.mkdir()
            (before / "index.html").write_text("<h1>Hello</h1>")
            (after / "index.html").write_text("<h1>  Hello  </h1>\n")
            changed, files = material_change(before, after)
            self.assertFalse(changed)
            self.assertEqual(files, [])

