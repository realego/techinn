"""Configure TechInn's inbound catch-all forwarding safely.

Run as root on the CyberPanel mail host. The explicit accounts mapping wins
over the catch-all, so accounts@techinn.co.zw remains excluded.
"""
from datetime import datetime
from pathlib import Path
import subprocess


DB = "cyberpanel"
DOMAIN = "techinn.co.zw"
DESTINATION = "support@technologyinn.co.zw"


def mysql(sql):
    return subprocess.run(["mysql", DB, "-e", sql], check=True, capture_output=True, text=True)


backup = Path("/root/techinn-backups") / f"techinn-forwardings-{datetime.now():%Y%m%d-%H%M%S}.sql"
backup.parent.mkdir(parents=True, exist_ok=True)
with backup.open("w") as handle:
    subprocess.run(["mysqldump", DB, "e_forwardings"], check=True, stdout=handle)

# Unknown addresses in this domain go to support. Existing exact mappings for
# accounts remain untouched and therefore take precedence over this wildcard.
mysql(
    "INSERT INTO e_forwardings (source, destination) "
    "SELECT '@techinn.co.zw', 'support@technologyinn.co.zw' "
    "WHERE NOT EXISTS (SELECT 1 FROM e_forwardings WHERE source='@techinn.co.zw' "
    "AND destination='support@technologyinn.co.zw')"
)

# Ensure current non-account service addresses also copy to support while
# preserving their mailbox delivery and existing forwarding destinations.
for source in ("info@techinn.co.zw", "sales@techinn.co.zw", "support@techinn.co.zw"):
    mysql(
        "INSERT INTO e_forwardings (source, destination) "
        f"SELECT '{source}', '{DESTINATION}' WHERE NOT EXISTS (SELECT 1 FROM e_forwardings "
        f"WHERE source='{source}' AND destination='{DESTINATION}')"
    )

subprocess.run(["postfix", "check"], check=True)
subprocess.run(["systemctl", "reload", "postfix"], check=True)
print(f"Configured {DOMAIN} catch-all forwarding to {DESTINATION}; accounts@{DOMAIN} remains excluded.")
print(f"Backup: {backup}")
