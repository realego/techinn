"""TechInn-owned website traffic enforcement.

CyberPanel status is advisory here. The guard is a reversible .htaccess layer
owned by TechInn and is applied to every document root recorded for a service.
"""
import html
import os
from pathlib import Path

from apps.services.models import HostingWebsite

class WebsiteSuspensionError(RuntimeError):
    pass

GUARD_FILE = ".techinn-suspension.htaccess"
BACKUP_FILE = ".techinn-original.htaccess"
PAGE_FILE = "techinn-suspended.html"
IMAGE_FILE = "techinn-suspended.png"
ROOT_PREFIX = Path("/home").resolve()


def _safe_root(value):
    path = Path(value).resolve()
    if path == ROOT_PREFIX or ROOT_PREFIX not in path.parents or not path.is_dir():
        raise ValueError("Website document root is outside the hosting filesystem.")
    return path


def _roots(service):
    account = getattr(service, "hosting_account", None)
    if not account:
        return []
    roots = []
    primary = getattr(account.primary_domain, "domain_name", "")
    if primary:
        roots.append(Path("/home") / primary / "public_html")
    roots.extend(
        Path(website.document_root)
        for website in HostingWebsite.objects.filter(hosting_account=account)
        if website.document_root
    )
    result = []
    for root in roots:
        try:
            safe = _safe_root(root)
        except (OSError, ValueError):
            continue
        if safe not in result:
            result.append(safe)
    return result


def suspend_websites(service):
    changed = 0
    for root in _roots(service):
        guard = root / GUARD_FILE
        original = root / ".htaccess"
        backup = root / BACKUP_FILE
        page = root / PAGE_FILE
        image = root / IMAGE_FILE
        try:
            if not guard.exists() and original.exists() and not backup.exists():
                original.replace(backup)
            if not guard.exists():
                guard.write_text(
                "RewriteEngine On\n"
                f"RewriteRule ^{PAGE_FILE}$ - [L]\n"
                f"RewriteRule ^.*$ {PAGE_FILE} [L]\n",
                encoding="utf-8",
                )
            domain = getattr(service.hosting_account.primary_domain, "domain_name", "TechInn website")
            preview_url = (service.provisioning_data or {}).get("preview_url", "")
            safe_preview = html.escape(preview_url, quote=True) if preview_url.startswith("https://") else ""
            image_source = Path(__file__).resolve().parents[2] / "assets" / IMAGE_FILE
            if image_source.exists():
                image.write_bytes(image_source.read_bytes())
                image.chmod(0o644)
            preview_link = (
                f'<p><a class="button secondary" href="{safe_preview}">Open website preview</a></p>'
                if safe_preview else ""
            )
            page.write_text(
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Website suspended</title>"
            "<style>:root{--orange:#f97316;--ink:#241812;--muted:#694b3a}*{box-sizing:border-box}body{font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;display:grid;place-items:center;min-height:100vh;margin:0;background:linear-gradient(135deg,#fffaf5 0%,#ffe6d2 50%,#ff9a55 100%);color:var(--ink)}main{width:min(760px,calc(100% - 32px));padding:34px 20px 44px;text-align:center}h1{margin:0 0 14px;font-size:clamp(2rem,6vw,4rem);letter-spacing:-.055em}p{color:var(--muted);line-height:1.65;margin:12px auto;max-width:560px}.art{display:block;width:min(460px,100%);max-height:42vh;object-fit:contain;margin:18px auto 20px}.button{display:inline-block;border-radius:999px;padding:11px 18px;background:var(--orange);color:white;text-decoration:none;font-weight:700;box-shadow:0 8px 22px #c2410c33}.button.secondary{background:#fff;color:#b45309;border:1px solid #fb923c}a{color:#b45309}footer{margin-top:26px;color:#8b5e47;font-size:.88rem}</style></head>"
            f"<body><main><h1>Website suspended</h1><img class=\"art\" src=\"/{IMAGE_FILE}\" alt=\"TechInn website suspended\"><p>This website for <strong>{html.escape(domain)}</strong> is temporarily unavailable because its hosting service needs attention.</p><p>If you are the owner, <a href=\"mailto:support@my.techinn.co.zw\">contact TechInn</a> or visit your <a href=\"https://my.techinn.co.zw/dashboard/billing/\">dashboard</a> to renew service.</p>{preview_link}<footer>Hosted by TechInn Hosting</footer></main></body></html>",
                encoding="utf-8",
            )
        except OSError as error:
            raise WebsiteSuspensionError(f"TechInn could not enforce the website suspension in {root}.") from error
        changed += 1
    return changed


def restore_websites(service):
    restored = 0
    for root in _roots(service):
        guard = root / GUARD_FILE
        backup = root / BACKUP_FILE
        page = root / PAGE_FILE
        image = root / IMAGE_FILE
        try:
            if guard.exists():
                guard.unlink()
            if backup.exists() and not (root / ".htaccess").exists():
                backup.replace(root / ".htaccess")
            if page.exists():
                page.unlink()
            if image.exists():
                image.unlink()
        except OSError as error:
            raise WebsiteSuspensionError(f"TechInn could not restore the website document root {root}.") from error
        restored += 1
    return restored
