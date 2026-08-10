# Authentication

OAuth2 Client Credentials flow. Confirmed against
`fedex/openapi/fedex-authorization-api-openapi.yml` (real portal export).

```
POST {base_url}/oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=<Client ID>&client_secret=<Client Secret>
```

Response:

```json
{"access_token": "...", "token_type": "bearer", "expires_in": 3600, "scope": "..."}
```

## Token handling

- Documented ~1 hour lifetime.
- Cached on **FedEx Connector Settings** (`fedex_access_token` /
  `fedex_token_expires_at`), refreshed automatically once close to expiry —
  not on every request.
- Base URL toggles between `apis.fedex.com` (production) and
  `apis-sandbox.fedex.com` (sandbox) via the settings form
  (`fedex_use_sandbox`).

## Two separate developer-portal projects

FedEx splits API access into two project categories that can't be
combined:

- **"Ship, Rate & other APIs"** — covers Ship, Rate, Address Validation,
  and most others.
- **"Basic Integrated Visibility"** (formerly named Track API) — its own
  separate project.

If you need both Track and Ship/Rate, create two FedEx dev-portal
projects. Each has its own Client ID/Secret — only one set can live on
`FedEx Connector Settings` at a time, since it's a Single doctype.

## Account Number

Ship, Rate, and Address Validation all require `fedex_account_number` on
Settings. For sandbox testing, use the project's **Sandbox Test Account**
number (auto-generated on the dev portal, separate from a real production
account number) — not your real one.

## Reachability check

FedEx has no generic `/ping` endpoint. `api/test_connection.py`'s
`test_connection()` performs the real OAuth exchange and reports success/
failure from that.

## Error handling

`fedex/client.py`'s `FedexClient.get`/`.post` (and the token fetch) retry
on `429`/`5xx`, honoring FedEx's own `Retry-After` header (see
`fedex/rate-limits/fedex-rate-limits.yml` — no public rate limit,
negotiated per contract). On terminal failure they raise `FedexAPIError`
with FedEx's real error code/message
(`{"errors": [{"code": "...", "message": "..."}]}`, consistent across
every v1 API) rather than a generic `requests.HTTPError`. Check
`error.status_code` and `error.fedex_errors`.
