import ipaddress
import logging
import re
import socket

import requests
from django.utils.html import strip_tags


logger = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = (".co.zw", ".com", ".net", ".online")
ZISPA_LOOKUP_URL = "https://zispa.org.zw/cgi-bin/domain_lookup.pl"
DOMAIN_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)

try:
    import whois
except ImportError:
    whois = None
    logger.warning("python-whois is not installed; domain search will rely on DNS and HTTP checks.")


def normalize_domain_name(value):
    domain = value.strip().lower().rstrip(".")
    if not DOMAIN_PATTERN.fullmatch(domain) or not domain.endswith(SUPPORTED_EXTENSIONS):
        raise ValueError("Enter a full domain using .co.zw, .com, .net or .online.")
    return domain


def _check_http(domain):
    try:
        addresses = socket.getaddrinfo(domain, 80, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return None

    public_addresses = []
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if ip.is_global and str(ip) not in public_addresses:
            public_addresses.append(str(ip))

    for address in public_addresses:
        host = f"[{address}]" if ":" in address else address
        try:
            response = requests.get(
                f"http://{host}/",
                headers={"Host": domain},
                timeout=5,
                allow_redirects=False,
            )
            response.close()
            return {
                "available": False,
                "status": "taken",
                "method": "http",
            }
        except requests.RequestException:
            continue
    return None


def _check_zispa(domain):
    response = None
    try:
        response = requests.get(
            ZISPA_LOOKUP_URL,
            params={"s": domain},
            headers={"User-Agent": "TechInn domain availability checker"},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        if response is not None:
            response.close()
        logger.warning("ZISPA lookup failed for %s: %s", domain, error)
        return {"available": None, "status": "unknown", "method": "zispa"}

    body = " ".join(strip_tags(response.text).split()).lower()
    response.close()
    if "is available for registration" in body:
        return {"available": True, "status": "available", "method": "zispa"}
    if domain in body and "registered" in body:
        return {"available": False, "status": "taken", "method": "zispa"}
    logger.warning("ZISPA returned an unrecognized availability response for %s", domain)
    return {"available": None, "status": "unknown", "method": "zispa"}


def check_domain_availability(domain):
    domain = normalize_domain_name(domain)

    if domain.endswith(".co.zw"):
        return _check_zispa(domain)

    try:
        socket.getaddrinfo(domain, None, type=socket.SOCK_STREAM)
        return {"available": False, "status": "taken", "method": "dns"}
    except socket.gaierror:
        pass

    if whois is not None:
        try:
            result = whois.whois(domain)
            registered_name = getattr(result, "domain_name", None)
            if not registered_name:
                return {"available": True, "status": "available", "method": "whois"}
            return {"available": False, "status": "taken", "method": "whois"}
        except Exception as error:
            logger.info("WHOIS lookup failed for %s: %s", domain, error)

    http_result = _check_http(domain)
    if http_result:
        return http_result

    return {"available": None, "status": "unknown", "method": "unconfirmed"}
