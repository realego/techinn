import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings


class CloudflareError(Exception):
    pass


def cloudflare_credentials(credentials):
    if isinstance(credentials, dict):
        token = credentials.get("api_token")
        if isinstance(token, str) and token.strip():
            return token.strip()
        email, key = credentials.get("email"), credentials.get("api_key")
        if isinstance(email, str) and email.strip() and isinstance(key, str) and key.strip():
            return {"email": email.strip(), "api_key": key.strip()}
    raise CloudflareError("Cloudflare credentials are missing or invalid.")


class CloudflareClient:
    base_url = "https://api.cloudflare.com/client/v4"

    def _request(self, token, method, path, payload=None, query=None):
        url = self.base_url + path
        if query:
            url += "?" + urlencode(query)
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        authentication = ({"X-Auth-Email": token["email"], "X-Auth-Key": token["api_key"]}
                          if isinstance(token, dict) else {"Authorization": f"Bearer {token}"})
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                **authentication,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "TechInn-Backend/1.0",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                response_data = json.loads(response.read())
        except HTTPError as error:
            raise CloudflareError(f"Cloudflare returned HTTP {error.code}.") from error
        except (URLError, TimeoutError) as error:
            raise CloudflareError("Could not connect to Cloudflare.") from error
        except json.JSONDecodeError as error:
            raise CloudflareError("Cloudflare returned an invalid response.") from error

        if not isinstance(response_data, dict) or not response_data.get("success"):
            raise CloudflareError("Cloudflare rejected the request; check token permissions and zone access.")
        result = response_data.get("result")
        if result is None:
            raise CloudflareError("Cloudflare response did not include a result.")
        return result

    def verify_token(self, token):
        if isinstance(token, dict):
            # Legacy global credentials have no token-verification endpoint.
            # A successful read validates access without creating or changing a zone.
            self.list_zones(token)
            return {"status": "active"}
        result = self._request(token, "GET", "/user/tokens/verify")
        if result.get("status") != "active":
            raise CloudflareError("Cloudflare API token is not active.")
        return result

    def list_zones(self, token):
        result = self._request(token, "GET", "/zones", query={"per_page": 50, "page": 1})
        if not isinstance(result, list):
            raise CloudflareError("Cloudflare returned an invalid zones list.")
        return result

    def onboard_zone(self, token, domain):
        zones = self._request(
            token,
            "GET",
            "/zones",
            query={"name": domain, "per_page": 1},
        )
        if not isinstance(zones, list):
            raise CloudflareError("Cloudflare returned an invalid zones list.")
        if zones:
            zone = zones[0]
        else:
            payload = {"name": domain, "jump_start": False}
            if settings.CLOUDFLARE_ACCOUNT_ID:
                payload["account"] = {"id": settings.CLOUDFLARE_ACCOUNT_ID}
            zone = self._request(token, "POST", "/zones", payload=payload)
        if (
            not isinstance(zone, dict)
            or not isinstance(zone.get("id"), str)
            or not isinstance(zone.get("name"), str)
            or zone.get("name", "").lower() != domain.lower()
        ):
            raise CloudflareError("Cloudflare returned an invalid zone.")
        nameservers = zone.get("name_servers", [])
        if not isinstance(nameservers, list) or any(not isinstance(item, str) for item in nameservers):
            raise CloudflareError("Cloudflare returned invalid nameservers.")
        return {
            "id": zone["id"],
            "name": zone["name"],
            "nameservers": nameservers,
            "status": zone.get("status", "pending"),
        }

    def get_zone(self, token, zone_id):
        result = self._request(token, "GET", f"/zones/{zone_id}")
        if not isinstance(result, dict):
            raise CloudflareError("Cloudflare returned an invalid zone.")
        return result

    def list_dns_records(self, token, zone_id):
        records = []
        page = 1
        while True:
            result = self._request(
                token,
                "GET",
                f"/zones/{zone_id}/dns_records",
                query={"per_page": 100, "page": page},
            )
            if not isinstance(result, list):
                raise CloudflareError("Cloudflare returned an invalid DNS records list.")
            records.extend(result)
            if len(result) < 100:
                return records
            page += 1

    def create_dns_record(self, token, zone_id, record):
        return self._request(token, "POST", f"/zones/{zone_id}/dns_records", payload=record)

    def update_dns_record(self, token, zone_id, record_id, record):
        return self._request(token, "PATCH", f"/zones/{zone_id}/dns_records/{record_id}", payload=record)

    def delete_dns_record(self, token, zone_id, record_id):
        return self._request(token, "DELETE", f"/zones/{zone_id}/dns_records/{record_id}")
