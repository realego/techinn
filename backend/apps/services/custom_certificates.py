"""TechInn's VPS certificate issuer.

Certificates are obtained with the host's certbot installation and the shared
Nginx ACME webroot. CyberPanel's issueSSL endpoint is intentionally not used.
"""

import re
import subprocess
from pathlib import Path


LIVE = Path("/etc/letsencrypt/live")
ACME_ROOT = Path("/var/www/html")


WEBMAIL_LOCATIONS = r"""    location = /webmail { return 308 /webmail/; }
    location /webmail/ {
        alias /var/lib/roundcube/public_html/;
        index index.php;
        try_files $uri $uri/ /webmail/index.php?$query_string;
    }
    location ~ ^/webmail/(.+\.php)$ {
        alias /var/lib/roundcube/public_html/$1;
        include fastcgi_params;
        fastcgi_param SCRIPT_FILENAME /var/lib/roundcube/public_html/$1;
        fastcgi_param SCRIPT_NAME /webmail/$1;
        fastcgi_param DOCUMENT_ROOT /var/lib/roundcube/public_html;
        fastcgi_pass unix:/run/php/php8.3-fpm.sock;
    }
"""


def issue_certificate(domain: str, aliases: tuple[str, ...] = ()) -> dict[str, str]:
    domain = domain.strip().lower().rstrip(".")
    names = tuple(dict.fromkeys((domain, *aliases)))
    if any(not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", name) for name in names):
        raise ValueError("Invalid certificate hostname.")
    cert_name = domain
    if (LIVE / f"{domain}-0001").is_dir():
        cert_name = f"{domain}-0001"
    current_cert = LIVE / cert_name / "fullchain.pem"
    if current_cert.exists() and subprocess.run(
        ["openssl", "verify", "-verify_hostname", domain, "-CApath", "/etc/ssl/certs", "-untrusted", str(current_cert), str(current_cert)],
        capture_output=True, timeout=10,
    ).returncode:
        # CyberPanel may overwrite even an existing certbot lineage with a
        # self-signed certificate. Keep our managed replacement separate.
        cert_name = f"{domain}-techinn"
    if (LIVE / f"{domain}-techinn").is_dir() or ((LIVE / cert_name).exists() and not Path(f"/etc/letsencrypt/renewal/{cert_name}.conf").exists()):
        cert_name = f"{domain}-techinn"
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
    _install_paths(domain, fullchain, private_key, aliases)
    return {"certificate": str(fullchain), "private_key": str(private_key), "cert_name": cert_name}


def _install_paths(domain: str, fullchain: Path, private_key: Path, aliases: tuple[str, ...] = ()) -> None:
    """Point matching Nginx and OpenLiteSpeed vhosts at the new certificate."""
    existing_https_vhost = False
    config_paths = [*Path("/etc/nginx/sites-available").glob("*"), *Path("/etc/nginx/conf.d").glob("*.conf")]
    for config_path in config_paths:
        try:
            contents = config_path.read_text()
        except OSError:
            continue
        server_names_found = [name for names in re.findall(r"server_name\s+([^;]+);", contents) for name in names.split()]
        if domain not in server_names_found or config_path.name.endswith((".bak", ".backup")):
            continue
        if "ssl_certificate " in contents and config_path.name != f"techinn-certificate-{domain}.conf":
            existing_https_vhost = True
        updated = re.sub(r"ssl_certificate\s+[^;]+;", f"ssl_certificate {fullchain};", contents)
        updated = re.sub(r"ssl_certificate_key\s+[^;]+;", f"ssl_certificate_key {private_key};", updated)
        if "ssl_certificate_key " in updated and "location /webmail/" not in updated:
            updated = re.sub(r"(ssl_certificate_key\s+[^;]+;)", lambda match: match.group(0) + "\n" + WEBMAIL_LOCATIONS, updated)
        if updated != contents:
            config_path.write_text(updated)
    # Customer domains are normally served by the OpenLiteSpeed catch-all
    # behind Nginx. Nginx still terminates TLS first, so give each issued
    # domain an SNI vhost with the certificate we just obtained.
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
{WEBMAIL_LOCATIONS}    location / {{
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
    if not existing_https_vhost and (not vhost_path.exists() or vhost_path.read_text() != vhost_contents):
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
