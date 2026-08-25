from __future__ import annotations

import ast
import hashlib
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
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
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ico",
    ".txt",
    ".webmanifest",
    ".woff",
    ".woff2",
}

TEXT_SUFFIXES = {
    ".html",
    ".htm",
    ".css",
    ".js",
    ".mjs",
    ".json",
    ".txt",
    ".webmanifest",
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

_NAVIGATION_RECEIVER = (
    r"(?<![\w$.'\"])(?:window|document|self|top|parent|globalThis)"
    r"\s*(?:(?:\?\s*)?\.\s*location|"
    r"(?:\?\s*\.\s*)?\[\s*['\"]location['\"]\s*\])"
    r"|(?<![\w$.'\"])location(?!\s*:)"
)
_NAVIGATION_ASSIGNMENT = (
    r"(?:>>>=|>>=|<<=|\*\*=|&&=|\|\|=|\?\?=|\+=|-=|\*=|/=|%=|&=|\^=|\|=|=)"
)
_LOCATION_MEMBER = (
    r"(?:(?:\?\s*)?\.\s*href|"
    r"(?:\?\s*\.\s*)?\[\s*['\"]href['\"]\s*\])"
)
_LOCATION_METHOD = (
    r"(?:(?:\?\s*)?\.\s*(?:assign|replace)|"
    r"(?:\?\s*\.\s*)?\[\s*['\"](?:assign|replace)['\"]\s*\])"
)
_WINDOW_OPEN = (
    r"(?<![\w$.'\"])(?:window|self|top|parent|globalThis)"
    r"\s*(?:(?:\?\s*)?\.\s*open|"
    r"(?:\?\s*\.\s*)?\[\s*['\"]open['\"]\s*\])"
)
_BARE_OPEN = r"(?<![\w$.'\"])open\s*\("

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
        rf"(?:"
        rf"(?:{_NAVIGATION_RECEIVER})\s*(?:"
        rf"{_NAVIGATION_ASSIGNMENT}"
        rf"|{_LOCATION_MEMBER}\s*{_NAVIGATION_ASSIGNMENT}"
        # A method reference is rejected even before it is called so aliases
        # such as location.assign.bind(location) cannot bypass this scan.
        rf"|{_LOCATION_METHOD}"
        rf")"
        rf"|{_WINDOW_OPEN}"
        rf"|{_BARE_OPEN}"
        rf")",
        re.I,
    ),
    "crypto mining": re.compile(r"\b(coinhive|cryptonight|webminer|stratum\+tcp)\b", re.I),
}

_JS_STATIC_STRING = r"""(?:'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")"""
_STATIC_STRING_CONCATENATION = re.compile(
    rf"(?P<chain>{_JS_STATIC_STRING}(?:\s*\+\s*{_JS_STATIC_STRING})+)"
)
_STATIC_STRING_LITERAL = re.compile(_JS_STATIC_STRING)

SECRET_PATTERNS = {
    "private key material": re.compile(
        r"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----"
    ),
    "GitHub access token": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"
    ),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "JWT-like credential": re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
    ),
    "assigned credential": re.compile(
        r"\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|secret)"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{20,}",
        re.I,
    ),
}

HOST_PATH_PATTERNS = {
    "private home path": re.compile(
        r"(?<![A-Za-z0-9_])/(?:home/[A-Za-z0-9._-]+|root)/"
        r"(?:\.ssh|\.aws|\.gnupg|\.secrets)(?:/[A-Za-z0-9._@+%/-]+)?"
    ),
    "Agent Farm private state path": re.compile(
        r"(?<![A-Za-z0-9_])/home/adminvince/projects/agent_farm/"
        r"(?:\.lab-state|\.secrets)(?:/[A-Za-z0-9._@+%/-]+)?"
    ),
    "sensitive system path": re.compile(
        r"(?<![A-Za-z0-9_])/etc/(?:passwd|shadow|sudoers|ssh/[A-Za-z0-9._-]+)\b"
    ),
    "local file URL": re.compile(
        r"\bfile:///(?:home/[A-Za-z0-9._-]+|root|etc)/[A-Za-z0-9._@+%/-]+",
        re.I,
    ),
    "Windows user path": re.compile(
        r"\b[A-Z]:\\Users\\[A-Za-z0-9._-]+\\(?:\.ssh|\.aws|\.gnupg)\\",
        re.I,
    ),
}

CSS_EXTERNAL_URL = re.compile(
    r"url\s*\(\s*['\"]?\s*(?:https?:)?//", re.I
)

CSP_FETCH_DIRECTIVES = {
    "child-src",
    "connect-src",
    "default-src",
    "font-src",
    "frame-src",
    "img-src",
    "manifest-src",
    "media-src",
    "object-src",
    "prefetch-src",
    "script-src",
    "script-src-attr",
    "script-src-elem",
    "style-src",
    "style-src-attr",
    "style-src-elem",
    "worker-src",
}

CSP_HARDENING_DIRECTIVES = {
    "block-all-mixed-content",
    "require-trusted-types-for",
    "trusted-types",
    "upgrade-insecure-requests",
}

CSP_SOURCE_KEYWORDS = {
    "'none'",
    "'report-sample'",
    "'self'",
    "'strict-dynamic'",
    "'unsafe-eval'",
    "'unsafe-hashes'",
    "'unsafe-inline'",
    "'wasm-unsafe-eval'",
}

CSP_NONCE_OR_HASH = re.compile(
    r"'(?:nonce-[A-Za-z0-9+/_-]+={0,2}|"
    r"sha(?:256|384|512)-[A-Za-z0-9+/_-]+={0,2})'",
    re.I,
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
            ".txt",
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
            name = words[0].lower()
            if name in directives:
                raise ValueError(f"duplicate CSP directive: {name}")
            directives[name] = {
                word.lower() if word.lower() in CSP_SOURCE_KEYWORDS else word
                for word in words[1:]
            }
    return directives


def _sources_at_least_as_strict(
    sources: set[str], allowed_sources: set[str], directive: str
) -> bool:
    if not sources or sources == {"'none'"}:
        return True
    if "'none'" in sources:
        return False

    for source in sources:
        if source in allowed_sources:
            continue
        if (
            directive.startswith(("script-src", "style-src"))
            and CSP_NONCE_OR_HASH.fullmatch(source)
        ):
            continue
        return False
    return True


def _csp_at_least_as_strict(policy: dict[str, set[str]]) -> bool:
    # All baseline directives stay explicit so a missing directive cannot silently
    # fall back to a weaker default. Additional fetch directives may only narrow
    # the baseline that they would otherwise inherit.
    for directive, allowed_sources in REQUIRED_CSP.items():
        sources = policy.get(directive)
        if sources is None or not _sources_at_least_as_strict(
            sources, allowed_sources, directive
        ):
            return False

    for directive, sources in policy.items():
        if directive in REQUIRED_CSP:
            continue
        if directive in CSP_HARDENING_DIRECTIVES:
            continue
        if directive not in CSP_FETCH_DIRECTIVES:
            return False
        if directive.startswith("script-src"):
            allowed_sources = REQUIRED_CSP["script-src"]
        elif directive.startswith("style-src"):
            allowed_sources = REQUIRED_CSP["style-src"]
        else:
            allowed_sources = REQUIRED_CSP["default-src"]
        if not _sources_at_least_as_strict(sources, allowed_sources, directive):
            return False
    return True


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
        self._csp_seen = False
        self._head_depth = 0
        self._script_depth = 0
        self._style_depth = 0
        self.script_parts: list[str] = []
        self.style_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        if tag == "head":
            self._head_depth += 1
        if tag in {
            "audio",
            "base",
            "embed",
            "form",
            "frame",
            "iframe",
            "object",
            "source",
            "svg",
            "track",
            "video",
        }:
            self.errors.append(f"{self.relative}: forbidden <{tag}> element")
        if "download" in values:
            self.errors.append(f"{self.relative}: download attributes are forbidden")
        if tag == "meta":
            if values.get("http-equiv", "").lower() == "refresh":
                self.errors.append(f"{self.relative}: meta refresh is forbidden")
            if values.get("http-equiv", "").lower() == "content-security-policy":
                if self._csp_seen:
                    self.errors.append(
                        f"{self.relative}: multiple content security policies are forbidden"
                    )
                elif not self._head_depth:
                    self.errors.append(
                        f"{self.relative}: content security policy must be in <head>"
                    )
                self._csp_seen = True
                try:
                    self.csp = _parse_csp(values.get("content", ""))
                except ValueError as exc:
                    self.errors.append(f"{self.relative}: invalid content security policy: {exc}")
        elif not self._csp_seen and (
            tag in {"img", "link", "script", "style"}
            or (tag == "input" and bool(values.get("src")))
            or bool(values.get("style"))
            or any(name.startswith("on") and value for name, value in values.items())
        ):
            self.errors.append(
                f"{self.relative}: content security policy must precede active content"
            )
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
        if tag.lower() == "head":
            self._head_depth = max(0, self._head_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._script_depth:
            self.script_parts.append(data)
        if self._style_depth:
            self.style_parts.append(data)


def _fold_static_string_concatenations(text: str) -> str:
    def merge(match: re.Match[str]) -> str:
        values: list[str] = []
        for literal in _STATIC_STRING_LITERAL.findall(match.group("chain")):
            try:
                value = ast.literal_eval(literal)
            except (SyntaxError, ValueError):
                return match.group(0)
            if not isinstance(value, str):
                return match.group(0)
            values.append(value)
        return repr("".join(values))

    return _STATIC_STRING_CONCATENATION.sub(merge, text)


def _check_script(text: str, label: str, report: ValidationReport) -> None:
    text = _fold_static_string_concatenations(text)
    for name, pattern in SCRIPT_PATTERNS.items():
        if pattern.search(text):
            report.reject(f"{label}: forbidden {name}")


def _check_sensitive_text(text: str, label: str, report: ValidationReport) -> None:
    # Never echo a match into the report: validation records may be published.
    for name, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            report.reject(f"{label}: possible {name} is forbidden")
    for name, pattern in HOST_PATH_PATTERNS.items():
        if pattern.search(text):
            report.reject(f"{label}: possible host-local {name} is forbidden")


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
        files: list[Path] = []
        for path in iter_regular_files(root):
            files.append(path)
            if len(files) > config.max_files:
                report.checked_files = len(files)
                report.reject("site exceeds file count limit")
                return report
    except ValueError as exc:
        report.reject(str(exc))
        return report

    report.checked_files = len(files)
    for path in files:
        relative = _relative(root, path)
        _check_sensitive_text(relative, "site path", report)
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
        text: str | None = None
        if suffix in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            _check_sensitive_text(text, relative, report)
        if suffix in {".js", ".mjs"}:
            assert text is not None
            _check_script(text, relative, report)
        elif suffix == ".css":
            assert text is not None
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
            if parser.csp is None or not _csp_at_least_as_strict(parser.csp):
                report.reject(
                    f"{relative}: content security policy is missing or weaker than required"
                )
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


def _remaining_browser_timeout_ms(deadline: float, per_operation_seconds: int) -> int:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("browser validation exceeded its total time limit")
    return max(1, int(min(remaining, per_operation_seconds) * 1000))


def validate_browser(
    root: Path,
    config: ValidationConfig,
    screenshot_dir: Path,
    report: ValidationReport,
) -> ValidationReport:
    deadline = time.monotonic() + config.browser_total_timeout_seconds
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
    allowed_origin = urlparse(base)
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    def external_origin(url: str) -> str | None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https", "ws", "wss"}:
            return None
        if (
            parsed.scheme == allowed_origin.scheme
            and parsed.hostname == allowed_origin.hostname
            and parsed.port == allowed_origin.port
        ):
            return None
        host = parsed.hostname or "unknown-host"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return f"{parsed.scheme}://{host}{port}"

    def configure_context(context: Any) -> None:
        def route_request(route: Any) -> None:
            destination = external_origin(route.request.url)
            if destination is not None:
                report.reject(
                    f"external browser request attempted: {destination}", browser=True
                )
                route.abort("blockedbyclient")
                return
            route.continue_()

        context.route("**/*", route_request)

    def configure_page(page: Any) -> tuple[Any, Any]:
        expected_url: list[str | None] = [None]

        def audit_frame(frame: Any) -> None:
            if frame != page.main_frame:
                return
            expected = expected_url[0]
            if expected is not None and frame.url != expected:
                report.reject(
                    "unexpected main-frame navigation attempted", browser=True
                )

        def audit_websocket(websocket: Any) -> None:
            destination = external_origin(websocket.url)
            if destination is not None:
                report.reject(
                    f"external browser websocket attempted: {destination}", browser=True
                )

        def expect(url: str) -> None:
            expected_url[0] = url

        def verify() -> None:
            audit_frame(page.main_frame)

        page.on("framenavigated", audit_frame)
        page.on("websocket", audit_websocket)
        return expect, verify

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                timeout=_remaining_browser_timeout_ms(
                    deadline, config.browser_timeout_seconds
                ),
            )
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            configure_context(context)
            page = context.new_page()
            expect_page_url, verify_page_url = configure_page(page)
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
                target_url = base + relative
                expect_page_url(target_url)
                response = page.goto(
                    target_url,
                    wait_until="networkidle",
                    timeout=_remaining_browser_timeout_ms(
                        deadline, config.browser_timeout_seconds
                    ),
                )
                verify_page_url()
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
            target_url = base + "/index.html"
            expect_page_url(target_url)
            page.goto(
                target_url,
                wait_until="networkidle",
                timeout=_remaining_browser_timeout_ms(
                    deadline, config.browser_timeout_seconds
                ),
            )
            verify_page_url()
            page.screenshot(
                path=str(desktop),
                full_page=True,
                timeout=_remaining_browser_timeout_ms(
                    deadline, config.browser_timeout_seconds
                ),
            )
            report.screenshots.append(desktop.name)
            context.close()

            mobile_context = browser.new_context(
                viewport={"width": 390, "height": 844},
                device_scale_factor=1,
                is_mobile=True,
            )
            configure_context(mobile_context)
            mobile_page = mobile_context.new_page()
            expect_mobile_url, verify_mobile_url = configure_page(mobile_page)
            target_url = base + "/index.html"
            expect_mobile_url(target_url)
            mobile_page.goto(
                target_url,
                wait_until="networkidle",
                timeout=_remaining_browser_timeout_ms(
                    deadline, config.browser_timeout_seconds
                ),
            )
            verify_mobile_url()
            mobile = screenshot_dir / "mobile.png"
            mobile_page.screenshot(
                path=str(mobile),
                full_page=True,
                timeout=_remaining_browser_timeout_ms(
                    deadline, config.browser_timeout_seconds
                ),
            )
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
    if not browser and config.require_browser:
        report.reject("browser validation is required", browser=True)
        return report
    if report.ok and browser:
        if screenshot_dir is None:
            raise ValueError("screenshot_dir is required for browser validation")
        validate_browser(root, config, screenshot_dir, report)
    return report
