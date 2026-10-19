from apps.services.models import HostingResource, Mailbox
from apps.services.providers.cyberpanel import CyberPanelError, set_linux_user_disk_quota


UNIT_TO_MB = {"gb": 1024, "gib": 1024, "mb": 1, "mib": 1}


def mailbox_storage_budget(account, *, excluding_mailbox=None):
    resource = account.resources.filter(resource_type=HostingResource.ResourceType.DISK).first()
    if not resource:
        return None
    conversion = UNIT_TO_MB.get(resource.unit.lower())
    if conversion is None:
        return {"invalid_unit": True}
    mailboxes = account.mailboxes.exclude(status=Mailbox.Status.DELETED)
    if excluding_mailbox is not None:
        mailboxes = mailboxes.exclude(pk=excluding_mailbox.pk)
    allocated_mb = sum(mailboxes.values_list("quota_mb", flat=True))
    limit_mb = int(resource.limit_value * conversion)
    web_used_mb = int(resource.used_value * conversion)
    return {
        "limit_mb": limit_mb,
        "web_used_mb": web_used_mb,
        "allocated_mb": allocated_mb,
        "available_mb": max(0, limit_mb - web_used_mb - allocated_mb),
    }


def set_shared_hosting_disk_quota(account, *, total_limit_gb=None):
    budget = mailbox_storage_budget(account)
    if budget is None:
        return
    if budget.get("invalid_unit"):
        raise CyberPanelError("The hosting storage limit uses an unsupported unit.")
    if not account.linux_username:
        raise CyberPanelError("The hosting account's filesystem owner has not been verified.")
    total_mb = budget["limit_mb"] if total_limit_gb is None else int(total_limit_gb * 1024)
    set_linux_user_disk_quota(
        account.linux_username,
        max(1, total_mb - budget["allocated_mb"]),
    )
