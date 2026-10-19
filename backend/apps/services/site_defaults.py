"""Safe default content for a newly provisioned customer website."""

import html
import os
import shutil
from pathlib import Path


def install_coming_soon_page(domain, linux_username=""):
    root = Path("/home") / domain / "public_html"
    root.mkdir(mode=0o755, parents=True, exist_ok=True)
    index = root / "index.html"
    # Never replace a customer's uploaded site. CyberPanel's fresh placeholder
    # is replaced, but any non-empty custom page is left untouched.
    existing = index.read_text(errors="ignore") if index.exists() else ""
    markers = ("CyberPanel", "Welcome to OpenLiteSpeed", "LiteSpeed", "Coming Soon")
    if existing.strip() and not any(marker.lower() in existing.lower() for marker in markers):
        return False
    safe_domain = html.escape(domain)
    image_name = "techinn-coming-soon.png"
    image_source = Path(__file__).resolve().parents[2] / "assets" / image_name
    image_target = root / image_name
    # Keep the provisioned asset in sync when the TechInn template is updated,
    # while leaving unrelated customer files untouched.
    if image_source.exists() and (
        not image_target.exists()
        or image_source.stat().st_mtime > image_target.stat().st_mtime
    ):
        shutil.copy2(image_source, image_target)
        if linux_username and os.geteuid() == 0:
            try:
                shutil.chown(image_target, user=linux_username, group=linux_username)
            except (KeyError, OSError):
                pass
        image_target.chmod(0o644)
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe_domain} | Coming soon</title>
<style>
:root{{--orange:#ff8a3d;--ink:#201b1a;--muted:#60483b}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:linear-gradient(135deg,#fff8f2 0%,#ffe7d4 44%,#ff9b55 100%);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif}}
main{{width:min(760px,calc(100% - 36px));padding:36px 20px 46px;text-align:center}}
h1{{margin:0 0 24px;font-size:clamp(2rem,6vw,4rem);letter-spacing:-.055em;color:var(--ink)}}
.art{{display:block;width:min(520px,100%);max-height:48vh;object-fit:contain;margin:0 auto 26px}}
p{{margin:0 auto;color:var(--muted);font-size:1.05rem;line-height:1.7;max-width:540px}}strong{{color:var(--ink)}}footer{{margin-top:28px;color:#805a46;font-size:.86rem}}a{{color:#b44f12;text-decoration:none;font-weight:700}}
</style></head><body><main><h1>Website Coming Soon</h1><img class="art" src="/{image_name}" alt="TechInn website coming soon"><p><strong>{safe_domain}</strong> is being prepared with TechInn Hosting. This website will be available here soon.</p><footer>Hosted securely by <a href="https://my.techinn.co.zw">TechInn Hosting</a></footer></main></body></html>'''
    index.write_text(page)
    if linux_username and os.geteuid() == 0:
        try:
            shutil.chown(index, user=linux_username, group=linux_username)
        except (KeyError, OSError):
            pass
    index.chmod(0o644)
    return True
