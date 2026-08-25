from __future__ import annotations

import hashlib
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.parse import unquote, urlparse

from .config import ValidationConfig


REQUIRED_CSP = {
    "default-src": {"'self'"},
    "script-src": {"'self'", "'unsafe-inline'"},
    "style-src": {"'self'", "'unsafe-inline'"},
    "img-src": {"'self'", "data:"},
    "font-src": {"'self'", "data:"},
    "connect-src": {"'none'"},
    "object-src": {"'none'"},
    "base-uri": {"'none'"},
    "form-action": {"'none'"},
    "frame-src": {"'none'"},
}

ALLOWED_SUFFIXES = {
    ".html",
    ".htm",
    ".css",
    ".js",
    ".mjs",
    ".json",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ico",
    ".txt",
    ".xml",
    ".webmanifest",
    ".woff",
    ".woff2",
}

FORBIDDEN_NAMES = {
    "opencode.json",
    "opencode.jsonc",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "requirements.txt",
    "pyproject.toml",
    "Dockerfile",
    "Makefile",
}

SCRIPT_PATTERNS = {
    "network request": re.compile(
        r"\b(fetch|XMLHttpRequest|WebSocket|EventSource|sendBeacon)\s*\(", re.I
    ),
    "service worker": re.compile(r"\bserviceWorker\b", re.I),
    "cookie access": re.compile(r"\bdocument\s*\.\s*cookie\b", re.I),
    "persistent browser storage": re.compile(r"\b(localStorage|sessionStorage|indexedDB)\b"),
    "dynamic code evaluation": re.compile(
        r"\b(eval\s*\(|new\s+Function\s*\(|set(?:Timeout|Interval)\s*\(\s*['\"])", re.I
    ),
    "obfuscated code": re.compile(r"\b(atob|String\s*\.\s*fromCharCode)\s*\(", re.I),
    "scripted redirect": re.compile(
        r"\b(?:window\s*\.\s*)?location(?:\s*\.\s*href)?\s*=", re.I
    ),
    "crypto mining": re.compile(r"\b(coinhive|cryptonight|webminer|stratum\+tcp)\b", re.I),
}

CSS_EXTERNAL_URL = re.compile(
    r"url\s*\(\s*['\"]?\s*(?:https?:)?//", re.I
)


@dataclass
class ValidationReport:
    ok: bool = True
    static_errors: list[str] = field(default_factory=list)
    browser_errors: list[str] = field(default_factory=list)
    checked_files: int = 0
    checked_pages: int = 0
    total_bytes: int = 0
    screenshots: list[str] = field(default_factory=list)

    def reject(self, message: str, *, browser: bool = False) -> None:
        self.ok = False
        target = self.browser_errors if browser else self.static_errors
        if message not in target:
            target.append(message)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def iter_regular_files(root: Path) -> Iterable[Path]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("site root must be a real directory")
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(directory)
        for dirname in list(dirnames):
            target = current / dirname
            if target.is_symlink():
                raise ValueError(f"symlinked directory is forbidden: {_relative(root, target)}")
        for filename in filenames:
            target = current / filename
            if target.is_symlink() or not target.is_file():
                raise ValueError(f"non-regular file is forbidden: {_relative(root, target)}")
            yield target


def content_manifest(root: Path) -> dict[str, dict[str, object]]:
    manifest: dict[str, dict[str, object]] = {}
    for path in sorted(iter_regular_files(root)):
        data = path.read_bytes()
        manifest[_relative(root, path)] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
        }
    return manifest


def material_change(before_root: Path, after_root: Path) -> tuple[bool, list[str]]:
    before = content_manifest(before_root)
    after = content_manifest(after_root)
    changed = sorted(
        path
        for path in set(before) | set(after)
        if before.get(path, {}).get("sha256") != after.get(path, {}).get("sha256")
    )
    meaningful: list[str] = []
    for relative in changed:
        old = before_root / relative
        new = after_root / relative
        if old.exists() and new.exists() and new.suffix.lower() in {
            ".html",
            ".htm",
            ".css",
            ".js",
            ".mjs",
            ".json",
            ".svg",
            ".txt",
            ".xml",
        }:
            old_text = re.sub(r"\s+", "", old.read_text(encoding="utf-8", errors="replace"))
            new_text = re.sub(r"\s+", "", new.read_text(encoding="utf-8", errors="replace"))
            if old_text == new_text:
                continue
        meaningful.append(relative)
    return bool(meaningful), meaningful


def _parse_csp(value: str) -> dict[str, set[str]]:
    directives: dict[str, set[str]] = {}
    for chunk in value.split(";"):
        words = chunk.strip().split()
        if words:
            directives[words[0].lower()] = set(words[1:])
    return directives


def _is_external_url(value: str) -> bool:
    stripped = value.strip().lower()
    return stripped.startswith(("http://", "https://", "//", "ftp://", "ws://", "wss://"))


class HtmlAudit(HTMLParser):
    def __init__(self, relative: str) -> None:
        super().__init__(convert_charrefs=True)
        self.relative = relative
        self.errors: list[str] = []
        self.local_links: list[str] = []
        self.csp: dict[str, set[str]] | None = None
        self._script_depth = 0
        self._style_depth = 0
        self.script_parts: list[str] = []
        self.style_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        if tag in {"form", "iframe", "frame", "object", "embed", "base"}:
            self.errors.append(f"{self.relative}: forbidden <{tag}> element")
        if "download" in values:
            self.errors.append(f"{self.relative}: download attributes are forbidden")
        if tag == "meta":
            if values.get("http-equiv", "").lower() == "refresh":
                self.errors.append(f"{self.relative}: meta refresh is forbidden")
            if values.get("http-equiv", "").lower() == "content-security-policy":
                self.csp = _parse_csp(values.get("content", ""))
        if tag == "script":
            self._script_depth += 1
        if tag == "style":
            self._style_depth += 1

        resource_attrs: list[str] = []
        if tag in {"script", "img", "audio", "video", "source", "track", "input"}:
            resource_attrs.append("src")
        if tag == "link":
            resource_attrs.append("href")
        for attr in resource_attrs:
            value = values.get(attr, "")
            if value and _is_external_url(value):
                self.errors.append(
                    f"{self.relative}: external runtime resource is forbidden: {value[:120]}"
                )

        href = values.get("href")
        if tag == "a" and href and not _is_external_url(href):
            parsed = urlparse(href)
            if parsed.scheme not in {"mailto", "tel", "javascript"}:
                self.local_links.append(href)
            if parsed.scheme == "javascript":
                self.errors.append(f"{self.relative}: javascript: links are forbidden")

        for name, value in values.items():
            if name.startswith("on") and value:
                self.script_parts.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script":
            self._script_depth = max(0, self._script_depth - 1)
        if tag.lower() == "style":
            self._style_depth = max(0, self._style_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._script_depth:
            self.script_parts.append(data)
        if self._style_depth:
            self.style_parts.append(data)


def _check_script(text: str, label: str, report: ValidationReport) -> None:
    for name, pattern in SCRIPT_PATTERNS.items():
        if pattern.search(text):
            report.reject(f"{label}: forbidden {name}")


def _resolve_local_link(root: Path, html_path: Path, link: str) -> Path | None:
    parsed = urlparse(link)
    if not parsed.path:
        return None
    path_text = unquote(parsed.path)
    if path_text.startswith("/"):
        target = root / path_text.lstrip("/")
    else:
        target = html_path.parent / path_text
    target = target.resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return Path("/__escape__")
    if target.is_dir():
        target = target / "index.html"
    return target


def validate_static(root: Path, config: ValidationConfig) -> ValidationReport:
    report = ValidationReport()
    index = root / "index.html"
    if not index.is_file() or index.is_symlink():
        report.reject("index.html is required")

    try:
        files = list(iter_regular_files(root))
    except ValueError as exc:
        report.reject(str(exc))
        return report

    report.checked_files = len(files)
    for path in files:
        relative = _relative(root, path)
        if any(part.startswith(".") for part in Path(relative).parts):
            report.reject(f"{relative}: hidden files and directories are forbidden")
        if path.name in FORBIDDEN_NAMES:
            report.reject(f"{relative}: forbidden project or harness file")
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            report.reject(f"{relative}: unsupported file type")
        size = path.stat().st_size
        report.total_bytes += size
        if size > config.max_file_bytes:
            report.reject(f"{relative}: exceeds per-file size limit")
        if path.stat().st_mode & 0o111:
            report.reject(f"{relative}: executable files are forbidden")

    if report.total_bytes > config.max_site_bytes:
        report.reject("site exceeds total size limit")

    for path in files:
        suffix = path.suffix.lower()
        relative = _relative(root, path)
        if suffix in {".js", ".mjs"}:
            _check_script(path.read_text(encoding="utf-8", errors="replace"), relative, report)
        elif suffix == ".css":
            text = path.read_text(encoding="utf-8", errors="replace")
            if CSS_EXTERNAL_URL.search(text):
                report.reject(f"{relative}: external CSS resource is forbidden")
        elif suffix in {".html", ".htm"}:
            parser = HtmlAudit(relative)
            try:
                parser.feed(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                report.reject(f"{relative}: invalid UTF-8 HTML: {exc}")
                continue
            for error in parser.errors:
                report.reject(error)
            if parser.csp != REQUIRED_CSP:
                report.reject(f"{relative}: required content security policy is missing or changed")
            _check_script("\n".join(parser.script_parts), relative, report)
            if CSS_EXTERNAL_URL.search("\n".join(parser.style_parts)):
                report.reject(f"{relative}: external inline CSS resource is forbidden")
            for link in parser.local_links:
                target = _resolve_local_link(root, path, link)
                if target and not target.is_file():
                    report.reject(f"{relative}: broken local link: {link}")

    return report


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def validate_browser(
    root: Path,
    config: ValidationConfig,
    screenshot_dir: Path,
    report: ValidationReport,
) -> ValidationReport:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        report.reject("Playwright is not installed", browser=True)
        return report

    handler = lambda *args, **kwargs: _QuietHandler(  # noqa: E731
        *args, directory=str(root), **kwargs
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            page.on(
                "console",
                lambda message: report.reject(
                    f"console {message.type}: {message.text}", browser=True
                )
                if message.type == "error"
                else None,
            )
            page.on("pageerror", lambda error: report.reject(f"page error: {error}", browser=True))

            pending = ["/index.html"]
            visited: set[str] = set()
            while pending and len(visited) < config.max_pages:
                relative = pending.pop(0)
                if relative in visited:
                    continue
                visited.add(relative)
                response = page.goto(
                    base + relative,
                    wait_until="networkidle",
                    timeout=config.browser_timeout_seconds * 1000,
                )
                if response is None or response.status >= 400:
                    status = "no response" if response is None else str(response.status)
                    report.reject(f"{relative}: browser returned {status}", browser=True)
                    continue
                links = page.eval_on_selector_all(
                    "a[href]",
                    "(els) => els.map((el) => el.getAttribute('href'))",
                )
                for link in links:
                    if not isinstance(link, str) or _is_external_url(link):
                        continue
                    parsed = urlparse(link)
                    if parsed.scheme in {"mailto", "tel"} or not parsed.path:
                        continue
                    resolved = str(
                        PurePosixPath(relative).parent.joinpath(parsed.path)
                    )
                    if parsed.path.startswith("/"):
                        resolved = parsed.path
                    if not resolved.startswith("/"):
                        resolved = "/" + resolved
                    if resolved.endswith("/"):
                        resolved += "index.html"
                    if Path(resolved).suffix.lower() in {".html", ".htm"}:
                        pending.append(resolved)

            desktop = screenshot_dir / "desktop.png"
            page.goto(base + "/index.html", wait_until="networkidle")
            page.screenshot(path=str(desktop), full_page=True)
            report.screenshots.append(desktop.name)
            context.close()

            mobile_context = browser.new_context(
                viewport={"width": 390, "height": 844},
                device_scale_factor=1,
                is_mobile=True,
            )
            mobile_page = mobile_context.new_page()
            mobile_page.goto(base + "/index.html", wait_until="networkidle")
            mobile = screenshot_dir / "mobile.png"
            mobile_page.screenshot(path=str(mobile), full_page=True)
            report.screenshots.append(mobile.name)
            mobile_context.close()
            browser.close()
            report.checked_pages = len(visited)
    except Exception as exc:
        report.reject(f"browser validation failed: {exc}", browser=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    return report


def validate_site(
    root: Path,
    config: ValidationConfig,
    screenshot_dir: Path | None = None,
    *,
    browser: bool = True,
) -> ValidationReport:
    report = validate_static(root, config)
    if report.ok and browser:
        if screenshot_dir is None:
            raise ValueError("screenshot_dir is required for browser validation")
        validate_browser(root, config, screenshot_dir, report)
    return report
