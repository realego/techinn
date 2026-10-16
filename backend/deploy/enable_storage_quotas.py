"""Enable shared website and per-mailbox storage enforcement on the hosting VPS."""
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


BACKUP = Path("/root/techinn-backups") / (
    "storage-quotas-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
)
CYBERPANEL = Path("/usr/local/CyberCP")
DOVECOT = Path("/etc/dovecot")
ROOT_FSTAB = Path("/etc/fstab")


def run(command, *, check=True, cwd=None, env=None):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            cwd=cwd,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"Could not run {Path(command[0]).name}.") from error
    if check and result.returncode != 0:
        raise RuntimeError(f"{Path(command[0]).name} failed.")
    return result


def atomic_write(path, content):
    metadata = path.stat()
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(temporary, metadata.st_uid, metadata.st_gid)
        os.chmod(temporary, metadata.st_mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def configure_dovecot():
    main_config = DOVECOT / "dovecot.conf"
    sql_config = DOVECOT / "dovecot-sql.conf.ext"
    main = main_config.read_text(encoding="utf-8")
    sql = sql_config.read_text(encoding="utf-8")

    main = re.sub(r"(?m)^mail_plugins = zlib$", "mail_plugins = zlib quota", main, count=1)
    main = re.sub(r"(?m)^    mail_plugins = zlib sieve$", "    mail_plugins = zlib sieve quota", main, count=1)
    main = re.sub(
        r"(?m)^    mail_plugins = \$mail_plugins zlib imap_zlib$",
        "    mail_plugins = $mail_plugins zlib imap_zlib imap_quota",
        main,
        count=1,
    )
    main = main.replace(
        "plugin {\n\n  zlib_save = gz",
        "plugin {\n  quota = maildir:User quota\n\n  zlib_save = gz",
        1,
    )
    required_settings = (
        "mail_plugins = zlib quota",
        "mail_plugins = zlib sieve quota",
        "mail_plugins = $mail_plugins zlib imap_zlib imap_quota",
        "quota = maildir:User quota",
    )
    if any(setting not in main for setting in required_settings):
        raise RuntimeError("The Dovecot configuration did not match the supported layout.")

    user_query = re.search(r"(?m)^user_query\s*=\s*(.+)$", sql)
    if not user_query:
        raise RuntimeError("The Dovecot SQL user query was not found.")
    query = user_query.group(1)
    if "techinn_mailbox_quotas" not in query:
        query = query.replace(", mail, CONCAT(", ", e_users.mail, CONCAT(", 1)
        query = query.replace(
            "SUBSTRING_INDEX(email,",
            "SUBSTRING_INDEX(e_users.email,",
        )
        expected = "as home FROM e_users WHERE email='%u'"
        replacement = (
            "as home, CASE WHEN techinn_quota.quota_mb IS NULL THEN '' "
            "ELSE CONCAT('*:storage=', techinn_quota.quota_mb, 'M') END AS quota_rule "
            "FROM e_users LEFT JOIN techinn_mailbox_quotas AS techinn_quota "
            "ON techinn_quota.email=e_users.email WHERE e_users.email='%u'"
        )
        if (
            expected not in query
            or "e_users.mail" not in query
            or query.count("SUBSTRING_INDEX(e_users.email,") != 2
        ):
            raise RuntimeError("The Dovecot SQL user query was not in the supported format.")
        sql = sql[:user_query.start(1)] + query.replace(expected, replacement, 1) + sql[user_query.end(1):]

    return main_config, main, sql_config, sql


def create_mail_quota_table():
    script = "\n".join((
        "from django.db import connection",
        "with connection.cursor() as cursor:",
        "    cursor.execute(\"CREATE TABLE IF NOT EXISTS techinn_mailbox_quotas (email VARCHAR(320) NOT NULL PRIMARY KEY, quota_mb INT UNSIGNED NOT NULL, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4\")",
        "    cursor.execute(\"ALTER TABLE techinn_mailbox_quotas MODIFY email VARCHAR(320) NOT NULL\")",
        "    cursor.execute(\"SELECT email, quota_mb FROM techinn_mailbox_quotas LIMIT 0\")",
    ))
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "CyberCP.settings"
    run(
        [str(CYBERPANEL / "bin/python"), "-c", script],
        cwd=CYBERPANEL,
        env=env,
    )


def root_user_quotas_enabled():
    result = run(["quotaon", "-p", "-u", "/"], check=False)
    output = f"{result.stdout}\n{result.stderr}".lower()
    if "user quota on /" in output and "is on" in output:
        return True
    if "user quota on /" in output and "is off" in output:
        return False
    if "no quota enabled" in output:
        return False
    raise RuntimeError("The current root quota state could not be checked.")


def enable_root_user_quotas():
    source, filesystem, options = run(
        ["findmnt", "-no", "SOURCE,FSTYPE,OPTIONS", "/"]
    ).stdout.strip().split(maxsplit=2)
    if filesystem != "ext4":
        raise RuntimeError("The root filesystem must be ext4 to enable user quotas.")
    quota_was_enabled = root_user_quotas_enabled()

    content = ROOT_FSTAB.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    root_entry = None
    for index, line in enumerate(lines):
        fields = line.split("#", 1)[0].split()
        if len(fields) >= 4 and fields[1] == "/" and fields[2] == "ext4":
            root_entry = (index, fields)
            break
    if root_entry is None:
        raise RuntimeError("An ext4 root entry was not found in /etc/fstab.")

    index, fields = root_entry
    mount_changed = False
    mount_options = fields[3].split(",")
    if "usrquota" not in mount_options:
        mount_options.append("usrquota")
        fields[3] = ",".join(mount_options)
        newline = "\n" if lines[index].endswith("\n") else ""
        lines[index] = "\t".join(fields) + newline
        atomic_write(ROOT_FSTAB, "".join(lines))
    if "usrquota" not in options.split(","):
        run(["mount", "-o", "remount,usrquota", "/"])
        mount_changed = True

    if quota_was_enabled:
        return True, mount_changed

    run(["quotacheck", "-c", "-u", "-m", "/"])
    run(["quotaon", "-u", "/"])
    status = run(["quotaon", "-p", "-u", "/"], check=False)
    status_output = f"{status.stdout}\n{status.stderr}".lower()
    if status.returncode not in (0, 1) or "user quota on /" not in status_output:
        raise RuntimeError("Root filesystem user quotas did not become active.")
    return quota_was_enabled, mount_changed


def restore_file(source, destination):
    shutil.copy2(source, destination)


def main():
    if os.geteuid() != 0:
        raise RuntimeError("Run this installer as root.")
    if not (DOVECOT / "dovecot.conf").is_file() or not (DOVECOT / "dovecot-sql.conf.ext").is_file():
        raise RuntimeError("The expected Dovecot configuration files were not found.")
    if not (CYBERPANEL / "bin/python").is_file():
        raise RuntimeError("CyberPanel's Python environment was not found.")
    if not shutil.which("quotaon") or not shutil.which("quotacheck"):
        raise RuntimeError("The Linux quota utilities are not installed.")
    if not list(Path("/usr/lib/dovecot/modules").glob("lib*_quota_plugin.so")):
        raise RuntimeError("The Dovecot quota plugin is not installed.")
    if not list(Path("/usr/lib/dovecot/modules").glob("lib*_imap_quota_plugin.so")):
        raise RuntimeError("The Dovecot IMAP quota plugin is not installed.")

    BACKUP.mkdir(parents=True, mode=0o700)
    saved_paths = (ROOT_FSTAB, DOVECOT / "dovecot.conf", DOVECOT / "dovecot-sql.conf.ext")
    for path in saved_paths:
        saved = BACKUP / path.relative_to("/")
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, saved)

    quota_was_enabled = root_user_quotas_enabled()
    mount_changed = False
    try:
        create_mail_quota_table()
        main_config, main_content, sql_config, sql_content = configure_dovecot()
        atomic_write(main_config, main_content)
        atomic_write(sql_config, sql_content)
        run(["doveconf", "-n"])
        lookup = run(
            ["doveadm", "user", "__techinn_quota_probe__@invalid.example"],
            check=False,
        )
        lookup_output = f"{lookup.stdout}\n{lookup.stderr}".lower()
        if lookup.returncode != 0 and not any(
            message in lookup_output for message in ("user not found", "doesn't exist")
        ):
            raise RuntimeError("Dovecot could not verify access to the mailbox quota table.")
        run(["systemctl", "reload", "dovecot"])
        run(["systemctl", "is-active", "--quiet", "dovecot"])
        quota_was_enabled, mount_changed = enable_root_user_quotas()
    except Exception:
        for path in saved_paths:
            restore_file(BACKUP / path.relative_to("/"), path)
        if mount_changed:
            run(["mount", "-o", "remount", "/"], check=False)
        if not quota_was_enabled:
            run(["quotaoff", "-u", "/"], check=False)
        run(["systemctl", "reload", "dovecot"], check=False)
        raise

    print(f"Storage quotas enabled. Configuration backups: {BACKUP}")


if __name__ == "__main__":
    main()
