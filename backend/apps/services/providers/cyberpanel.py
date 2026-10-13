"""CyberPanel API operations used by the service provisioning workers."""
import json
import os
import re
import secrets
import subprocess
import string

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
            "openBasedir": "PHP",
        })
        if str(result.get("existsStatus", "0")) == "1":
            result["already_exists"] = True
        elif str(result.get("createWebSiteStatus", result.get("status", "0"))) != "1":
            raise CyberPanelError("CyberPanel could not create the website.")
        result.setdefault("websiteOwner", username)
        return result

    def set_website_status(self, *, domain, state):
        if state not in {"Suspend", "Un-Suspend"}:
            raise CyberPanelError("Unsupported CyberPanel website status change.")
        result = self._post("submitWebsiteStatus", {"websiteName": domain, "state": state})
        if not isinstance(result, dict) or str(result.get("websiteStatus", "0")) != "1":
            raise CyberPanelError("CyberPanel could not change the website status.")
        return result


def run_local_mail_operation(*, operation, domain, local_part, password=None):
    """Call CyberPanel's own mail utility without putting passwords in argv."""
    if operation not in {"create", "delete", "change_password"}:
        raise CyberPanelError("Unsupported CyberPanel mail operation.")
    if not re.fullmatch(r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}", domain):
        raise CyberPanelError("Invalid mailbox domain.")
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}", local_part):
        raise CyberPanelError("Invalid mailbox name.")
    if operation in {"create", "change_password"} and (not password or len(password) < 8):
        raise CyberPanelError("Mailbox passwords must contain at least 8 characters.")
    if operation == "create":
        # Follow the working portal: use the supported command and independently
        # confirm creation through the mail server's JSON mailbox listing.
        env = os.environ.copy()
        env["DJANGO_SETTINGS_MODULE"] = "CyberCP.settings"
        address = f"{local_part.lower()}@{domain.lower()}"

        def existing_addresses():
            result = subprocess.run(
                ["/usr/bin/cyberpanel", "listEmailsJson", "--domainName", domain.lower()],
                capture_output=True, text=True, timeout=30, check=False, env=env,
            )
            if result.returncode != 0:
                raise CyberPanelError("The mail server could not check existing mailboxes.")
            try:
                rows = json.loads(result.stdout.strip())
                if isinstance(rows, str):
                    rows = json.loads(rows)
                return {row["email"].lower() for row in rows}
            except (ValueError, TypeError, KeyError):
                raise CyberPanelError("The mail server returned an unreadable mailbox list.")

        try:
            if address in existing_addresses():
                # A previous create may have reached the server before the worker
                # lost its confirmation. A retry includes a new customer-chosen
                # password, so apply it to the existing mailbox and confirm it.
                run_local_mail_operation(
                    operation="change_password", domain=domain,
                    local_part=local_part, password=password,
                )
                if address not in existing_addresses():
                    raise CyberPanelError("The existing mailbox could not be confirmed after its password update.")
                return {"ok": True, "already_exists": True}
            result = subprocess.run(
                ["/usr/bin/cyberpanel", "createEmail", "--domainName", domain.lower(),
                 "--userName", local_part.lower(), "--password", password],
                capture_output=True, text=True, timeout=60, check=False, env=env,
            )
            created = address in existing_addresses()
        except (OSError, subprocess.SubprocessError) as error:
            raise CyberPanelError("The mail server could not complete mailbox creation.") from error
        if not created:
            try:
                response = json.loads(result.stdout.strip())
            except (ValueError, TypeError):
                response = {}
            detail = str(response.get("errorMessage") or result.stderr.strip()
                         or "The mail server did not confirm the new mailbox.")[:180]
            detail = detail.replace(address, "this mailbox").replace(password, "[hidden]")
            raise CyberPanelError(detail)
        return {"ok": True}

    script = "\n".join((
        "import json, sys",
        "from plogical.mailUtilities import mailUtilities",
        "d = json.load(sys.stdin)",
        "if d['operation'] == 'create':",
        "    result = mailUtilities.createEmailAccount(d['domain'], d['local_part'], d['password'])",
        "elif d['operation'] == 'change_password':",
        "    result = mailUtilities.changeEmailPassword(d['email'], d['password'])",
        "    result = (1, 'None') if result == (0, 'None') else result",
        "else:",
        "    result = mailUtilities.deleteEmailAccount(d['email'])",
        "print(json.dumps({'ok': bool(result and result[0] == 1), 'message': str(result[1]) if result and len(result) > 1 else ''}))",
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
            timeout=60, check=True, env=env,
        )
        result = json.loads(completed.stdout.splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as error:
        raise CyberPanelError("CyberPanel mailbox operation failed.") from error
    if not result.get("ok"):
        message = str(result.get("message") or "CyberPanel did not confirm the operation.")[:240]
        message = message.replace(payload["email"], "the mailbox")
        if password:
            message = message.replace(password, "[hidden]")
        raise CyberPanelError(f"CyberPanel could not complete this mailbox change: {message}")
