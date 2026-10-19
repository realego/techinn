import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models


class EncryptedTextField(models.TextField):
    description = "Text encrypted at rest with Fernet"
    prefix = "fernet:v1:"

    @staticmethod
    def _cipher():
        key = getattr(settings, "DATA_ENCRYPTION_KEY", "")
        if not key:
            raise ImproperlyConfigured("DATA_ENCRYPTION_KEY must be configured.")
        try:
            return Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as error:
            raise ImproperlyConfigured(
                "DATA_ENCRYPTION_KEY must be a valid URL-safe base64 Fernet key."
            ) from error

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ""):
            return value
        if value.startswith(self.prefix):
            return value
        encrypted = self._cipher().encrypt(value.encode("utf-8")).decode("ascii")
        return self.prefix + encrypted

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        if not value.startswith(self.prefix):
            raise ImproperlyConfigured("Refusing to read an unencrypted provider credential.")
        try:
            return self._cipher().decrypt(value[len(self.prefix):].encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeEncodeError, UnicodeDecodeError) as error:
            raise ImproperlyConfigured(
                "Could not decrypt a provider credential; verify DATA_ENCRYPTION_KEY."
            ) from error

    def to_python(self, value):
        return value


def encrypt_secret(value):
    """Encrypt a short-lived secret before placing it in a JSON action payload."""
    if not value:
        return ""
    return EncryptedTextField._cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value):
    if not value:
        return ""
    try:
        return EncryptedTextField._cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError, UnicodeDecodeError) as error:
        raise ImproperlyConfigured("Could not decrypt a queued secret.") from error
