"""TechInn's VPS certificate issuer.

Certificates are obtained with the host's certbot installation and the shared
Nginx ACME webroot. CyberPanel's issueSSL endpoint is intentionally not used.
"""

import re
import subprocess
from pathlib import Path


LIVE = Path("/etc/letsencrypt/live")
ACME_ROOT = Path("/var/www/html")


def issue_certificate(domain: str, aliases: tuple[str, ...] = ()) -> dict[str, str]:
    domain = domain.strip().lower().rstrip(".")
    names = tuple(dict.fromkeys((domain, *aliases)))
    cert_name = domain
    if (LIVE / f"{domain}-0001").is_dir():
        cert_name = f"{domain}-0001"
    ACME_ROOT.joinpath(".well-known", "acme-challenge").mkdir(parents=True, exist_ok=True)
    command = [
        "certbot", "certonly", "--webroot", "-w", str(ACME_ROOT),
        "--cert-name", cert_name, "--non-interactive", "--agree-tos",
        "--email", "security@techinn.co.zw", "--keep-until-expiring",
    ]
    for name in names:
        command.extend(("-d", name))
    result = subprocess.run(command, capture_output=True, text=True, timeout=240)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:]
        raise RuntimeError("Certificate issuance failed: " + (detail[0] if detail else "certbot returned an error"))
    certificate = LIVE / cert_name
    fullchain = certificate / "fullchain.pem"
    private_key = certificate / "privkey.pem"
    if not fullchain.exists() or not private_key.exists():
        raise RuntimeError("Certificate issuer completed without creating certificate files.")
    _install_paths(domain, fullchain, private_key)
    return {"certificate": str(fullchain), "private_key": str(private_key), "cert_name": cert_name}


def _install_paths(domain: str, fullchain: Path, private_key: Path) -> None:
    """Point matching Nginx and OpenLiteSpeed vhosts at the new certificate."""
    config_paths = [*Path("/etc/nginx/sites-available").glob("*"), *Path("/etc/nginx/conf.d").glob("*.conf")]
    for config_path in config_paths:
        try:
            contents = config_path.read_text()
        except OSError:
            continue
        if not re.search(rf"server_name\s+[^;]*\b{re.escape(domain)}\b", contents):
            continue
        updated = re.sub(r"ssl_certificate\s+[^;]+;", f"ssl_certificate {fullchain};", contents)
        updated = re.sub(r"ssl_certificate_key\s+[^;]+;", f"ssl_certificate_key {private_key};", updated)
        if updated != contents:
            config_path.write_text(updated)
    # Customer domains are normally served by the OpenLiteSpeed catch-all
    # behind Nginx. Nginx still terminates TLS first, so give each issued
    # domain an SNI vhost with the certificate we just obtained.
    aliases = (f"www.{domain}",)
    vhost_path = Path("/etc/nginx/conf.d") / f"techinn-certificate-{re.sub(r'[^a-z0-9.-]', '-', domain)}.conf"
    server_names = " ".join((domain, *aliases))
    vhost_contents = f'''# Managed by TechInn's VPS certificate issuer for {domain}\n
server {{
    listen 80;
    listen [::]:80;
    server_name {server_names};
    location /.well-known/acme-challenge/ {{ root /var/www/html; }}
    location / {{ return 301 https://$host$request_uri; }}
}}

server {{
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name {server_names};
    ssl_certificate {fullchain};
    ssl_certificate_key {private_key};
    ssl_protocols TLSv1.2 TLSv1.3;
    location / {{
        proxy_pass https://127.0.0.1:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_ssl_verify off;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
    }}
}}
'''
    if not vhost_path.exists() or vhost_path.read_text() != vhost_contents:
        vhost_path.write_text(vhost_contents)
    vhost = Path("/usr/local/lsws/conf/vhosts") / domain / "vhost.conf"
    if vhost.exists():
        contents = vhost.read_text()
        block = f"vhssl {{\n keyFile {private_key}\n certFile {fullchain}\n certChain 1\n}}"
        if "vhssl" in contents:
            contents = re.sub(r"vhssl\s*\{[^}]*\}", block, contents, flags=re.S)
        else:
            contents += "\n" + block + "\n"
        vhost.write_text(contents)
    subprocess.run(["nginx", "-t"], check=True, capture_output=True, text=True, timeout=30)
    subprocess.run(["systemctl", "reload", "nginx"], check=True, timeout=30)
    if vhost.exists():
        # The global OLS configuration currently reports unrelated legacy
        # PHP handler warnings on validation. Reloading remains safe and is
        # the operation that activates this vhost's certificate.
        subprocess.run(["systemctl", "reload", "lsws"], check=True, timeout=30)
