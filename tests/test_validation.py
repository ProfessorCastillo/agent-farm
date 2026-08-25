from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from agent_lab.config import ValidationConfig
from agent_lab.validation import (
    REQUIRED_CSP,
    _remaining_browser_timeout_ms,
    material_change,
    validate_site,
    validate_static,
)


def csp_text(policy: dict[str, set[str]] | None = None) -> str:
    policy = REQUIRED_CSP if policy is None else policy
    return "; ".join(
        f"{directive} {' '.join(sorted(values))}"
        for directive, values in policy.items()
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
    max_files=100,
    max_pages=10,
    browser_timeout_seconds=5,
    browser_total_timeout_seconds=20,
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

    def test_stricter_csp_is_accepted(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            policy = {name: set(values) for name, values in REQUIRED_CSP.items()}
            policy["script-src"] = {"'self'"}
            html = page().replace(csp_text(), csp_text(policy))
            (root / "index.html").write_text(html)
            report = validate_static(root, CONFIG)
            self.assertTrue(report.ok, report.static_errors)

    def test_nonce_and_hash_csp_sources_are_accepted(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            policy = {name: set(values) for name, values in REQUIRED_CSP.items()}
            policy["script-src"] = {"'self'", "'nonce-bm9uY2UtaWQtMTIzNDU2'"}
            policy["style-src"] = {
                "'self'",
                "'sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU='",
            }
            (root / "index.html").write_text(
                page().replace(csp_text(), csp_text(policy))
            )
            report = validate_static(root, CONFIG)
            self.assertTrue(report.ok, report.static_errors)

    def test_weaker_or_unknown_widening_csp_is_rejected(self) -> None:
        policies: list[dict[str, set[str]]] = []
        weak_script = {name: set(values) for name, values in REQUIRED_CSP.items()}
        weak_script["script-src"].add("https:")
        policies.append(weak_script)
        weak_worker = {name: set(values) for name, values in REQUIRED_CSP.items()}
        weak_worker["worker-src"] = {"*"}
        policies.append(weak_worker)
        unknown = {name: set(values) for name, values in REQUIRED_CSP.items()}
        unknown["future-src"] = {"*"}
        policies.append(unknown)
        strict_dynamic = {name: set(values) for name, values in REQUIRED_CSP.items()}
        strict_dynamic["script-src"] = {"'self'", "'strict-dynamic'"}
        policies.append(strict_dynamic)

        for policy in policies:
            with self.subTest(policy=policy), TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "index.html").write_text(
                    page().replace(csp_text(), csp_text(policy))
                )
                report = validate_static(root, CONFIG)
                self.assertFalse(report.ok)
                self.assertTrue(
                    any("weaker than required" in error for error in report.static_errors)
                )

    def test_csp_must_precede_active_content(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(
                "<!doctype html><html><head><script>const ready = true</script>"
                f'<meta http-equiv="Content-Security-Policy" content="{csp_text()}">'
                "</head><body></body></html>"
            )
            report = validate_static(root, CONFIG)
            self.assertFalse(report.ok)
            self.assertTrue(
                any("must precede active content" in error for error in report.static_errors)
            )

    def test_csp_must_precede_input_image_resource(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(
                "<!doctype html><html><head><input type=\"image\" src=\"button.png\">"
                f'<meta http-equiv="Content-Security-Policy" content="{csp_text()}">'
                "</head><body></body></html>"
            )
            report = validate_static(root, CONFIG)
            self.assertFalse(report.ok)
            self.assertTrue(
                any("must precede active content" in error for error in report.static_errors)
            )

    def test_forms_are_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(page(body="<form><input></form>"))
            report = validate_static(root, CONFIG)
            self.assertFalse(report.ok)
            self.assertTrue(any("forbidden <form>" in error for error in report.static_errors))

    def test_media_elements_are_rejected(self) -> None:
        for element in ("audio", "video", "source", "track"):
            with self.subTest(element=element), TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "index.html").write_text(page(body=f"<{element}>"))
                report = validate_static(root, CONFIG)
                self.assertFalse(report.ok)
                self.assertTrue(
                    any(
                        f"forbidden <{element}>" in error
                        for error in report.static_errors
                    )
                )

    def test_svg_files_are_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(page())
            (root / "active.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
            )
            report = validate_static(root, CONFIG)
            self.assertFalse(report.ok)
            self.assertTrue(
                any("active.svg: unsupported file type" in error for error in report.static_errors)
            )

    def test_inline_svg_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(
                page(body='<svg><animate attributeName="href"></animate></svg>')
            )
            report = validate_static(root, CONFIG)
            self.assertFalse(report.ok)
            self.assertTrue(
                any("forbidden <svg>" in error for error in report.static_errors)
            )

    def test_xml_files_are_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(page())
            (root / "active.xml").write_text(
                '<?xml-stylesheet href="https://evil.example/site.xsl"?>'
            )
            report = validate_static(root, CONFIG)
            self.assertFalse(report.ok)
            self.assertTrue(
                any("active.xml: unsupported file type" in error for error in report.static_errors)
            )

    def test_redirect_sinks_are_rejected_without_property_false_positive(self) -> None:
        redirects = (
            "location.assign('/next')",
            "location.replace('/next')",
            "window.location = '/next'",
            "document.location.href = '/next'",
            "self.location.assign('/next')",
            "top.location.replace('/next')",
            "globalThis.location = '/next'",
            "window['location'] = '/next'",
            "location['href'] = '/next'",
            "location.href += '?next'",
            "window.open('/next')",
            "globalThis['open']('/next')",
            "window?.location?.assign('/next')",
            "globalThis?.['open']('/next')",
            "open('/next')",
            "const go = window.open; go('/next')",
            "const go = location.assign.bind(location); go('/next')",
            "window['loc' + 'ation'] = '/next'",
            "window['op' + 'en']('/next')",
        )
        for script in redirects:
            with self.subTest(script=script), TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "index.html").write_text(page(script=script))
                report = validate_static(root, CONFIG)
                self.assertFalse(report.ok)
                self.assertTrue(
                    any("scripted redirect" in error for error in report.static_errors)
                )

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(
                page(script="const weather = {}; weather.location = 'coast'")
            )
            report = validate_static(root, CONFIG)
            self.assertTrue(report.ok, report.static_errors)

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(
                page(script="const weather = {}; weather['loc' + 'ation'] = 'coast'")
            )
            report = validate_static(root, CONFIG)
            self.assertTrue(report.ok, report.static_errors)

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(
                page(script="const foo = {window: {location: ''}}; foo.window.location = 'coast'")
            )
            report = validate_static(root, CONFIG)
            self.assertTrue(report.ok, report.static_errors)

    def test_secrets_and_host_paths_are_rejected_without_echoing_values(self) -> None:
        token = "ghp_" + "a" * 36
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(
                page(
                    body="<pre>/home/adminvince/.ssh/id_ed25519</pre>",
                    script=f"const access_token = '{token}'",
                )
            )
            report = validate_static(root, CONFIG)
            self.assertFalse(report.ok)
            joined = "\n".join(report.static_errors)
            self.assertIn("host-local private home path", joined)
            self.assertIn("GitHub access token", joined)
            self.assertNotIn(token, joined)

    def test_required_browser_validation_cannot_be_skipped(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(page())
            report = validate_site(root, CONFIG, browser=False)
            self.assertFalse(report.ok)
            self.assertIn("browser validation is required", report.browser_errors)

    def test_browser_operations_use_remaining_total_deadline(self) -> None:
        with patch("agent_lab.validation.time.monotonic", return_value=100.0):
            self.assertEqual(_remaining_browser_timeout_ms(102.5, 30), 2500)
        with patch("agent_lab.validation.time.monotonic", return_value=103.0):
            with self.assertRaises(TimeoutError):
                _remaining_browser_timeout_ms(102.5, 30)

    def test_site_file_count_is_bounded(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(page())
            (root / "extra.txt").write_text("extra")
            report = validate_static(root, replace(CONFIG, max_files=1))
            self.assertFalse(report.ok)
            self.assertIn("site exceeds file count limit", report.static_errors)

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
