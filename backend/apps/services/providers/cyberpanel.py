"""CyberPanel API operations used by the service provisioning workers."""
import base64
import hashlib
import hmac
import json
import os
import pwd
import re
import secrets
import shutil
import subprocess
import string
import time
from pathlib import Path

import requests
from django.conf import settings


class CyberPanelError(RuntimeError):
    pass


def generate_owner_password(length=24):
    alphabet = string.ascii_letters + string.digits + "!@#$%_-"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def cyberpanel_credentials(connection=None):
    if connection:
        try:
            values = json.loads(connection.credentials)
        except (TypeError, json.JSONDecodeError) as error:
            raise CyberPanelError("The stored CyberPanel connection is invalid.") from error
        return values.get("api_url", "").rstrip("/"), values.get("api_user", ""), values.get("api_password", "")
    return (
        settings.CYBERPANEL_API_URL,
        settings.CYBERPANEL_API_USER,
        settings.CYBERPANEL_API_PASSWORD,
    )


class CyberPanelClient:
    def __init__(self, connection=None):
        self.base_url, self.admin_user, self.admin_pass = cyberpanel_credentials(connection)
        self.timeout = 25

    @property
    def configured(self):
        return bool(self.base_url and self.admin_user and self.admin_pass)

    def _post(self, endpoint, payload=None):
        if not self.configured:
            raise CyberPanelError("CyberPanel API is not configured.")
        body = {"adminUser": self.admin_user, "adminPass": self.admin_pass, **(payload or {})}
        try:
            response = requests.post(
                f"{self.base_url}/api/{endpoint}", json=body, timeout=self.timeout, verify=True
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as error:
            raise CyberPanelError(f"CyberPanel {endpoint} request failed.") from error
        return data

    def verify(self):
        result = self._post("listPackage", {})
        # CyberPanel returns package names directly for successful requests,
        # while its authentication failures return a JSON object.
        if not isinstance(result, list):
            raise CyberPanelError("CyberPanel rejected the configured credentials.")
        return result

    def create_website(self, *, domain, email, owner_password, package, php=None):
        domain = domain.strip().rstrip(".").lower()
        if not re.fullmatch(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain):
            raise CyberPanelError("Invalid hosting domain.")
        if not package.strip():
            raise CyberPanelError("A CyberPanel package mapping is required for this hosting plan.")
        username = "ti" + re.sub(r"[^a-z0-9]", "", email.lower().split("@", 1)[0])[:24]
        result = self._post("createWebsite", {
            "domainName": domain,
            "ownerEmail": email,
            "packageName": package,
            "websiteOwner": username,
            "ownerPassword": owner_password,
            "phpSelection": php or settings.CYBERPANEL_PHP,
            "ssl": 1,
            "dkim": 1,
            "openBasedir": 1,
        })
        if str(result.get("existsStatus", "0")) == "1":
            result["already_exists"] = True
        elif str(result.get("createWebSiteStatus", result.get("status", "0"))) != "1":
            raise CyberPanelError("CyberPanel could not create the website: " + str(result.get("error_message", "Unknown provider error"))[:300])
        result.setdefault("websiteOwner", username)
        # The panel username is NOT the Linux filesystem owner.
        # Verify the resulting website and its owner before granting access.
        script = """
import os, sys, json
sys.path.insert(0, '/usr/local/CyberCP')
os.environ['DJANGO_SETTINGS_MODULE'] = 'CyberCP.settings'
import django; django.setup()
from websiteFunctions.models import Websites
d = json.load(sys.stdin)
s = Websites.objects.select_related('admin').get(domain=d['domain'])
if s.admin.email.lower() != d['email'].lower():
    raise ValueError('Website belongs to another customer')
print(json.dumps({'websiteOwner': s.admin.userName, 'linux_username': s.externalApp}))
"""
        try:
            checked = subprocess.run(['/usr/local/CyberCP/bin/python', '-c', script],
                input=json.dumps({'domain': domain, 'email': email}), text=True,
                capture_output=True, timeout=30, check=True)
            result.update(json.loads(checked.stdout))
        except (subprocess.SubprocessError, ValueError, OSError) as error:
            raise CyberPanelError('Website was created but its filesystem ownership could not be verified.') from error
        return result
    def set_website_status(self, *, domain, state):
        if state not in {"Suspend", "Un-Suspend"}:
            raise CyberPanelError("Unsupported CyberPanel website status change.")
        result = self._post("submitWebsiteStatus", {"websiteName": domain, "state": state})
        if not isinstance(result, dict) or str(result.get("websiteStatus", "0")) != "1":
            raise CyberPanelError("CyberPanel could not change the website status.")
        return result

    def issue_ssl(self, *, domain):
        """Issue/renew a public certificate with TechInn's VPS issuer."""
        try:
            from apps.services.custom_certificates import issue_certificate
            return issue_certificate(domain, (f"www.{domain}",))
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
            raise CyberPanelError(str(error)) from error

    def issue_mail_ssl(self, *, hostname):
        """Issue a mail-host certificate with TechInn's VPS issuer."""
        try:
            from apps.services.custom_certificates import issue_certificate
            return issue_certificate(hostname)
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as error:
            raise CyberPanelError(str(error)) from error

    def create_child_website(self, *, master_domain, child_domain, username, plan_expires):
        if not self.configured:
            raise CyberPanelError("CyberPanel API is not configured.")
        try:
            secret = Path("/etc/techinn/portal-sso.key").read_bytes()
        except OSError as error:
            raise CyberPanelError("Secure CyberPanel provisioning is unavailable.") from error
        payload = {
            "master_domain": master_domain,
            "child_domain": child_domain,
            "username": username,
            "plan_expires": plan_expires,
            "issued_at": time.time(),
            "nonce": secrets.token_hex(32),
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        signature = hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()
        try:
            response = requests.post(
                f"{self.base_url}/api/techinn/create-child/",
                json={"ticket": f"{encoded}.{signature}"},
                headers={"Origin": "https://my.techinn.co.zw"},
                timeout=(5, 80),
                verify=True,
            )
            result = response.json()
        except (requests.RequestException, ValueError) as error:
            raise CyberPanelError("CyberPanel could not create the subdomain website.") from error
        if response.status_code >= 400:
            detail = result.get("detail") if isinstance(result, dict) else None
            raise CyberPanelError(
                detail if isinstance(detail, str) and detail else
                "The subdomain website could not be created. Check your hosting plan and try again."
            )
        if (
            not isinstance(result, dict)
            or result.get("success") is not True
            or result.get("domain") != child_domain
            or not isinstance(result.get("document_root"), str)
        ):
            detail = result.get("detail") if isinstance(result, dict) else None
            raise CyberPanelError(
                detail if isinstance(detail, str) and detail else
                "The subdomain website could not be created. Check your hosting plan and try again."
            )
        return result

    def install_child_certificate(self, *, master_domain, child_domain, username, plan_expires):
        if not self.configured:
            raise CyberPanelError("Secure website certificate installation is unavailable.")
        try:
            secret = Path("/etc/techinn/portal-sso.key").read_bytes()
        except OSError as error:
            raise CyberPanelError("Secure website certificate installation is unavailable.") from error
        payload = {
            "master_domain": master_domain,
            "child_domain": child_domain,
            "username": username,
            "plan_expires": plan_expires,
            "issued_at": time.time(),
            "nonce": secrets.token_hex(32),
        }
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        signature = hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()
        try:
            response = requests.post(
                f"{self.base_url}/api/techinn/install-certificate/",
                json={"ticket": f"{encoded}.{signature}"},
                headers={"Origin": "https://my.techinn.co.zw"},
                timeout=(5, 180),
                verify=True,
            )
            result = response.json()
        except (requests.RequestException, ValueError) as error:
            raise CyberPanelError("The website certificate could not be installed. Check DNS and try again.") from error
        if (
            response.status_code >= 400
            or not isinstance(result, dict)
            or result.get("success") is not True
            or result.get("domain") != child_domain
        ):
            detail = result.get("detail") if isinstance(result, dict) else None
            raise CyberPanelError(
                detail if isinstance(detail, str) and detail else
                "The website certificate could not be installed. Check DNS and try again."
            )
        return result


def set_linux_user_disk_quota(username, limit_mb):
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username or ""):
        raise CyberPanelError("The hosting filesystem owner is invalid.")
    try:
        pwd.getpwnam(username)
    except KeyError as error:
        raise CyberPanelError("The hosting filesystem owner does not exist.") from error
    if not isinstance(limit_mb, int) or limit_mb < 1:
        raise CyberPanelError("The hosting storage limit must be at least 1 MB.")
    quotaon = shutil.which("quotaon")
    setquota = shutil.which("setquota")
    if not quotaon or not setquota or os.geteuid() != 0:
        raise CyberPanelError("Filesystem storage enforcement is not available.")
    try:
        enabled = subprocess.run(
            [quotaon, "-p", "-u", "/"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        enabled_output = f"{enabled.stdout}\n{enabled.stderr}".lower()
        if "user quota on /" not in enabled_output or "is on" not in enabled_output:
            raise CyberPanelError("Filesystem storage enforcement is not enabled.")
        result = subprocess.run(
            [setquota, "-u", username, f"{limit_mb}M", f"{limit_mb}M", "0", "0", "/"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise CyberPanelError("The hosting storage limit could not be applied.") from error
    if result.returncode != 0:
        raise CyberPanelError("The hosting storage limit could not be applied.")


def run_local_mail_quota_operation(*, operation, domain, local_part, quota_mb=None):
    if operation not in {"set", "delete"}:
        raise CyberPanelError("Unsupported mailbox storage operation.")
    if not re.fullmatch(r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}", domain):
        raise CyberPanelError("Invalid mailbox domain.")
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}", local_part):
        raise CyberPanelError("Invalid mailbox name.")
    if operation == "set" and (not isinstance(quota_mb, int) or quota_mb < 1):
        raise CyberPanelError("Mailbox storage allocation must be at least 1 MB.")
    script = "\n".join((
        "import json, sys",
        "from django.db import connection",
        "d = json.load(sys.stdin)",
        "with connection.cursor() as cursor:",
        "    cursor.execute(\"CREATE TABLE IF NOT EXISTS techinn_mailbox_quotas (email VARCHAR(320) NOT NULL PRIMARY KEY, quota_mb INT UNSIGNED NOT NULL, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4\")",
        "    if d['operation'] == 'set':",
        "        cursor.execute('INSERT INTO techinn_mailbox_quotas (email, quota_mb) VALUES (%s, %s) ON DUPLICATE KEY UPDATE quota_mb=VALUES(quota_mb)', [d['email'], d['quota_mb']])",
        "    else:",
        "        cursor.execute('DELETE FROM techinn_mailbox_quotas WHERE email=%s', [d['email']])",
        "print(json.dumps({'ok': True}))",
    ))
    email = f"{local_part.lower()}@{domain.lower()}"
    payload = {"operation": operation, "email": email, "quota_mb": quota_mb}
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "CyberCP.settings"
    try:
        result = subprocess.run(
            ["/usr/local/CyberCP/bin/python", "-c", script],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
            env=env,
            cwd="/usr/local/CyberCP",
        )
        response = json.loads(result.stdout.splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as error:
        raise CyberPanelError("The mailbox storage allocation could not be saved.") from error
    if response.get("ok") is not True:
        raise CyberPanelError("The mailbox storage allocation could not be saved.")
    if operation == "set":
        doveadm = shutil.which("doveadm")
        if not doveadm:
            raise CyberPanelError("Mailbox storage enforcement is not available.")
        try:
            result = subprocess.run(
                [doveadm, "quota", "recalc", "-u", email],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise CyberPanelError(
                "The mail storage service is unavailable, so the mailbox storage limit could not be applied. Retry after the mail service is healthy."
            ) from error
        if result.returncode != 0:
            raise CyberPanelError(
                "The mail storage service could not enforce this mailbox storage limit. Retry after the mail service is healthy."
            )


def run_local_mail_operation(*, operation, domain, local_part, password=None):
    """Call CyberPanel's own mail utility without putting passwords in argv."""
    if operation not in {"create", "delete", "change_password", "clear_storage"}:
        raise CyberPanelError("Unsupported CyberPanel mail operation.")
    if not re.fullmatch(r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}", domain):
        raise CyberPanelError("Invalid mailbox domain.")
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}", local_part):
        raise CyberPanelError("Invalid mailbox name.")
    if operation in {"create", "change_password"} and (not password or len(password) < 8):
        raise CyberPanelError("Mailbox passwords must contain at least 8 characters.")
    if operation == "clear_storage":
        doveadm = shutil.which("doveadm")
        if not doveadm:
            raise CyberPanelError("Mailbox storage cleanup is not available.")
        email = f"{local_part.lower()}@{domain.lower()}"

        def run_doveadm(command, failure_message):
            try:
                result = subprocess.run(
                    command, capture_output=True, text=True, timeout=120, check=False,
                )
            except (OSError, subprocess.SubprocessError) as error:
                raise CyberPanelError(failure_message) from error
            if result.returncode != 0:
                detail = (result.stderr or result.stdout).strip()
                detail = detail.replace(email, "this mailbox")[:180]
                suffix = f": {detail}" if detail else ""
                raise CyberPanelError(f"{failure_message}{suffix}")
            return result

        mailbox_result = run_doveadm(
            [doveadm, "mailbox", "list", "-u", email],
            "Mailbox folders could not be listed.",
        )
        mailboxes = [name.strip() for name in mailbox_result.stdout.splitlines() if name.strip()]
        for mailbox_name in mailboxes:
            run_doveadm(
                [doveadm, "expunge", "-u", email, "mailbox", mailbox_name, "ALL"],
                "Stored mailbox messages could not be cleared.",
            )
        run_doveadm(
            [doveadm, "quota", "recalc", "-u", email],
            "Mailbox usage could not be recalculated.",
        )
        try:
            result = subprocess.run(
                [doveadm, "-f", "tab", "quota", "get", "-u", email],
                capture_output=True, text=True, timeout=60, check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise CyberPanelError("Mailbox storage cleanup could not be verified.") from error
        if result.returncode != 0:
            raise CyberPanelError("Mailbox storage cleanup could not be verified.")
        storage_rows = [
            line.split("\t")
            for line in result.stdout.splitlines()[1:]
            if len(line.split("\t")) >= 3 and line.split("\t")[1] == "STORAGE"
        ]
        if len(storage_rows) != 1:
            raise CyberPanelError("Mailbox storage cleanup could not be verified.")
        try:
            remaining_kb = int(storage_rows[0][2])
        except ValueError as error:
            raise CyberPanelError("Mailbox storage cleanup could not be verified.") from error
        if remaining_kb != 0:
            raise CyberPanelError("Some mailbox storage remains in use; the cleanup was not confirmed.")
        update_usage_script = "\n".join((
            "import json, sys",
            "import django",
            "django.setup()",
            "from mailServer.models import EUsers",
            "d = json.load(sys.stdin)",
            "updated = EUsers.objects.filter(email=d['email']).update(DiskUsage='0')",
            "print(json.dumps({'updated': updated}))",
        ))
        env = os.environ.copy()
        env["DJANGO_SETTINGS_MODULE"] = "CyberCP.settings"
        try:
            result = subprocess.run(
                ["/usr/local/CyberCP/bin/python", "-c", update_usage_script],
                input=json.dumps({"email": email}),
                capture_output=True, text=True, timeout=30, check=True,
                cwd="/usr/local/CyberCP", env=env,
            )
            if json.loads(result.stdout.splitlines()[-1]).get("updated") != 1:
                raise CyberPanelError("Mailbox usage could not be recorded after cleanup.")
        except (OSError, subprocess.SubprocessError, ValueError, IndexError) as error:
            raise CyberPanelError("Mailbox usage could not be recorded after cleanup.") from error
        return {"ok": True, "used_mb": 0}
    script = "\n".join((
        "import json, shutil, sys, bcrypt",
        "import django",
        "django.setup()",
        "from pathlib import Path",
        "from django.db import transaction",
        "from mailServer.models import EUsers",
        "from plogical.mailUtilities import mailUtilities",
        "d = json.load(sys.stdin)",
        "already_exists = EUsers.objects.filter(email=d['email']).exists()",
        "if d['operation'] == 'create':",
        "    if already_exists:",
        "        result = mailUtilities.changeEmailPassword(d['email'], d['password'])",
        "        result = (1, 'None') if result == (0, 'None') else result",
        "    else:",
        "        result = mailUtilities.createEmailAccount(d['domain'], d['local_part'], d['password'])",
        "elif d['operation'] == 'change_password':",
        "    result = mailUtilities.changeEmailPassword(d['email'], d['password'])",
        "    result = (1, 'None') if result == (0, 'None') else result",
        "else:",
        "    root = Path('/home/vmail').resolve()",
        "    domain_root = root / d['domain']",
        "    resolved_domain_root = domain_root.resolve()",
        "    if resolved_domain_root.parent != root:",
        "        raise ValueError('Mailbox domain storage path is outside the mail storage root.')",
        "    account_path = domain_root / d['local_part']",
        "    if account_path.parent != domain_root or account_path.name in ('', '.', '..'):",
        "        raise ValueError('Invalid mailbox storage path.')",
        "    with transaction.atomic():",
        "        EUsers.objects.filter(email=d['email']).delete()",
        "    if account_path.is_symlink():",
        "        account_path.unlink()",
        "    elif account_path.exists():",
        "        resolved_account_path = account_path.resolve()",
        "        if resolved_account_path.parent != resolved_domain_root:",
        "            raise ValueError('Mailbox storage path is outside its domain.')",
        "        shutil.rmtree(resolved_account_path)",
        "    result = (1, 'None')",
        "if d['operation'] in ('create', 'change_password') and result and result[0] == 1:",
        "    account = EUsers.objects.filter(email=d['email']).first()",
        "    if not account or not bcrypt.checkpw(d['password'].encode(), account.password.removeprefix('{CRYPT}').encode()):",
        "        result = (0, 'The mailbox password could not be verified.')",
        "print(json.dumps({'ok': bool(result and result[0] == 1), 'already_exists': already_exists, 'message': str(result[1]) if result and len(result) > 1 else ''}))",
    ))
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "CyberCP.settings"
    payload = {
        "operation": operation,
        "domain": domain.lower(),
        "local_part": local_part.lower(),
        "email": f"{local_part.lower()}@{domain.lower()}",
        "password": password or "",
    }
    try:
        completed = subprocess.run(
            ["/usr/local/CyberCP/bin/python", "-c", script],
            input=json.dumps(payload), capture_output=True, text=True,
            timeout=60, check=True, cwd="/usr/local/CyberCP", env=env,
        )
        result = json.loads(completed.stdout.splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as error:
        raise CyberPanelError("The mail server could not complete this mailbox change.") from error
    if not result.get("ok"):
        message = str(result.get("message") or "CyberPanel did not confirm the operation.")[:240]
        message = message.replace(payload["email"], "the mailbox")
        if password:
            message = message.replace(password, "[hidden]")
        raise CyberPanelError(f"CyberPanel could not complete this mailbox change: {message}")
    if operation == "create":
        return result
