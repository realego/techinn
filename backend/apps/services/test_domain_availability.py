import socket
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import requests

from apps.services.domain_availability import check_domain_availability, normalize_domain_name


class DomainAvailabilityTests(TestCase):
    @patch("apps.services.domain_availability.socket.getaddrinfo")
    @patch("apps.services.domain_availability.whois.whois")
    @patch("apps.services.domain_availability.requests.get")
    def test_co_zw_uses_zispa_availability_response(self, lookup, whois_lookup, resolve):
        response = Mock()
        response.text = (
            "The domain <b>kundatest.co.zw</b> is available for registration, "
            "subject to ZISPA's standard Terms and Conditions."
        )
        lookup.return_value = response

        result = check_domain_availability("kundatest.co.zw")

        self.assertEqual(result, {"available": True, "status": "available", "method": "zispa"})
        lookup.assert_called_once_with(
            "https://zispa.org.zw/cgi-bin/domain_lookup.pl",
            params={"s": "kundatest.co.zw"},
            headers={"User-Agent": "TechInn domain availability checker"},
            timeout=10,
        )
        response.close.assert_called_once()
        whois_lookup.assert_not_called()
        resolve.assert_not_called()

    @patch("apps.services.domain_availability.requests.get")
    def test_co_zw_registered_domain_is_unavailable(self, lookup):
        response = Mock()
        response.text = (
            'The domain google.co.zw is already registered by "Markmonitor" '
            "with the following NS records: ns1.google.com."
        )
        lookup.return_value = response

        result = check_domain_availability("google.co.zw")

        self.assertEqual(result, {"available": False, "status": "taken", "method": "zispa"})
        response.close.assert_called_once()

    @patch(
        "apps.services.domain_availability.requests.get",
        side_effect=requests.RequestException("ZISPA unavailable"),
    )
    def test_co_zw_lookup_errors_remain_unknown(self, lookup):
        result = check_domain_availability("unknown.co.zw")

        self.assertEqual(result, {"available": None, "status": "unknown", "method": "zispa"})
        lookup.assert_called_once()

    @patch("apps.services.domain_availability.requests.get")
    def test_unrecognized_zispa_response_remains_unknown(self, lookup):
        response = Mock()
        response.text = "<p>Domain lookup service maintenance</p>"
        lookup.return_value = response

        result = check_domain_availability("unknown.co.zw")

        self.assertEqual(result, {"available": None, "status": "unknown", "method": "zispa"})

    @patch("apps.services.domain_availability.whois.whois")
    @patch("apps.services.domain_availability.socket.getaddrinfo")
    def test_dns_resolution_marks_domain_as_taken(self, resolve, lookup):
        resolve.return_value = [("AF_INET", "SOCK_STREAM", 6, "", ("203.0.113.10", 0))]

        result = check_domain_availability("Example.com")

        self.assertEqual(result, {"available": False, "status": "taken", "method": "dns"})
        lookup.assert_not_called()

    @patch("apps.services.domain_availability.whois.whois")
    @patch("apps.services.domain_availability.socket.getaddrinfo", side_effect=socket.gaierror)
    def test_whois_confirms_unregistered_domain(self, resolve, lookup):
        lookup.return_value = SimpleNamespace(domain_name=None)

        result = check_domain_availability("example.com")

        self.assertEqual(result, {"available": True, "status": "available", "method": "whois"})
        lookup.assert_called_once_with("example.com")
        self.assertEqual(resolve.call_count, 1)

    @patch("apps.services.domain_availability.whois.whois")
    @patch("apps.services.domain_availability.socket.getaddrinfo", side_effect=socket.gaierror)
    def test_whois_registered_domain_is_taken(self, resolve, lookup):
        lookup.return_value = SimpleNamespace(domain_name="example.com")

        result = check_domain_availability("example.com")

        self.assertEqual(result, {"available": False, "status": "taken", "method": "whois"})
        self.assertEqual(resolve.call_count, 1)

    @patch("apps.services.domain_availability.requests.get")
    @patch(
        "apps.services.domain_availability.whois.whois",
        side_effect=RuntimeError("WHOIS unavailable"),
    )
    @patch(
        "apps.services.domain_availability.socket.getaddrinfo",
        side_effect=[
            socket.gaierror(),
            [("AF_INET", "SOCK_STREAM", 6, "", ("1.1.1.1", 80))],
        ],
    )
    def test_http_fallback_uses_public_ip_and_host_header(self, resolve, lookup, get):
        response = Mock()
        get.return_value = response

        result = check_domain_availability("example.com")

        self.assertEqual(result, {"available": False, "status": "taken", "method": "http"})
        get.assert_called_once_with(
            "http://1.1.1.1/",
            headers={"Host": "example.com"},
            timeout=5,
            allow_redirects=False,
        )
        response.close.assert_called_once()
        self.assertEqual(resolve.call_count, 2)

    @patch(
        "apps.services.domain_availability.whois.whois",
        side_effect=RuntimeError("WHOIS unavailable"),
    )
    @patch(
        "apps.services.domain_availability.socket.getaddrinfo",
        side_effect=[socket.gaierror(), [("AF_INET", "SOCK_STREAM", 6, "", ("127.0.0.1", 80))]],
    )
    def test_http_fallback_never_targets_private_addresses(self, resolve, lookup):
        result = check_domain_availability("example.com")

        self.assertEqual(result, {"available": None, "status": "unknown", "method": "unconfirmed"})
        self.assertEqual(resolve.call_count, 2)

    def test_only_supported_tlds_are_accepted(self):
        self.assertEqual(normalize_domain_name("EXAMPLE.CO.ZW."), "example.co.zw")
        with self.assertRaises(ValueError):
            normalize_domain_name("example.invalid")
