import os
import base64
import hashlib
import json
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "development-only-change-this-before-deployment",
)
if not DEBUG and SECRET_KEY == "development-only-change-this-before-deployment":
    raise RuntimeError("Set DJANGO_SECRET_KEY to a strong secret when DEBUG is false.")
DATA_ENCRYPTION_KEY = os.getenv("DATA_ENCRYPTION_KEY")
if not DATA_ENCRYPTION_KEY and DEBUG:
    DATA_ENCRYPTION_KEY = base64.urlsafe_b64encode(
        hashlib.sha256(SECRET_KEY.encode("utf-8")).digest()
    ).decode("ascii")
if not DEBUG and not DATA_ENCRYPTION_KEY:
    raise RuntimeError("Set DATA_ENCRYPTION_KEY to encrypt provider credentials at rest.")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "apps.accounts",
    "apps.catalog",
    "apps.orders",
    "apps.billing",
    "apps.services",
    "apps.notifications",
    "apps.automation",
    "apps.core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "techinn_api.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]
WSGI_APPLICATION = "techinn_api.wsgi.application"
ASGI_APPLICATION = "techinn_api.asgi.application"

if os.getenv("DB_ENGINE", "sqlite").lower() == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME", "techinn"),
            "USER": os.getenv("DB_USER", "techinn"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.getenv("SQLITE_PATH", str(BASE_DIR / "db.sqlite3")),
        }
    }

AUTH_USER_MODEL = "accounts.Customer"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Harare"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.sessions.IdleJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "auth": "10/hour",
        "domain_verification": "6/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=6),
    "TOKEN_REFRESH_SERIALIZER": "apps.accounts.sessions.IdleRefreshSerializer",
}

GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
CHECKOUT_TEST_EMAIL = os.getenv("CHECKOUT_TEST_EMAIL", "").strip().casefold()
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").lower() == "true"
if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise RuntimeError("Configure only one of EMAIL_USE_TLS or EMAIL_USE_SSL.")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "TechInn <accounts@my.techinn.co.zw>")

CYBERPANEL_API_URL = os.getenv("CYBERPANEL_API_URL", "").rstrip("/")
CYBERPANEL_API_USER = os.getenv("CYBERPANEL_API_USER", "")
CYBERPANEL_API_PASSWORD = os.getenv("CYBERPANEL_API_PASSWORD", "")
CYBERPANEL_PACKAGE_WEB_BASIC = os.getenv("CYBERPANEL_PACKAGE_WEB_BASIC", "")
CYBERPANEL_PACKAGE_WEB_GROWTH = os.getenv("CYBERPANEL_PACKAGE_WEB_GROWTH", "")
CYBERPANEL_PACKAGE_WEB_BUSINESS = os.getenv("CYBERPANEL_PACKAGE_WEB_BUSINESS", "")
CYBERPANEL_PHP = os.getenv("CYBERPANEL_PHP", "PHP 8.2")

PAYNOW_ID = os.getenv("PAYNOW_ID", "")
PAYNOW_KEY = os.getenv("PAYNOW_KEY", "")
PAYNOW_EMAIL = os.getenv("PAYNOW_EMAIL", "")
PAYNOW_RETURN_URL = os.getenv("PAYNOW_RETURN_URL", "")
PAYNOW_RESULT_URL = os.getenv("PAYNOW_RESULT_URL", "")

CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_CONNECTION_NAME = os.getenv("CLOUDFLARE_CONNECTION_NAME", "TechInn Cloudflare")
ZISPA_API_URL = os.getenv("ZISPA_API_URL", "").rstrip("/")
ZISPA_SUBMISSIONS_ENABLED = os.getenv("ZISPA_SUBMISSIONS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
DOMAIN_REGISTRATION_LOCK_DIR = BASE_DIR / "var" / "domain-registration-locks"
ZISPA_API_KEY = os.getenv("ZISPA_API_KEY", "")
ZISPA_DRAFT_API_KEY = os.getenv("ZISPA_DRAFT_API_KEY", "")
ZISPA_AUTO_SEND = os.getenv("ZISPA_AUTO_SEND", "false").lower() in {"1", "true", "yes", "on"}
try:
    ZISPA_DEFAULT_NAMESERVERS = json.loads(os.getenv("ZISPA_DEFAULT_NAMESERVERS", "[]"))
except json.JSONDecodeError as error:
    raise RuntimeError("ZISPA_DEFAULT_NAMESERVERS must be a valid JSON list.") from error
if not isinstance(ZISPA_DEFAULT_NAMESERVERS, list) or any(
    not isinstance(item, dict)
    or not isinstance(item.get("hostname"), str)
    or not isinstance(item.get("ip"), str)
    for item in ZISPA_DEFAULT_NAMESERVERS
):
    raise RuntimeError("ZISPA_DEFAULT_NAMESERVERS must contain hostname and ip entries.")

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,https://my.techinn.co.zw",
    ).split(",")
    if origin.strip()
]

SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

TECHINN_HOSTING_IPV4 = os.getenv("TECHINN_HOSTING_IPV4", "")
TECHINN_WEBMAIL_URL = os.getenv("TECHINN_WEBMAIL_URL", "https://techinn.co.zw/webmail/")
