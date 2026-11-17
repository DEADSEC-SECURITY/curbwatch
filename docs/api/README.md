# API contracts

The owner API requires account sessions; mutations require JSON, same-origin validation and X-CSRF-Token. Email/user/SSO/sharing administration requires an administrator. The separate viewer uses restricted bearer tokens, never account cookies, and returns aggregated map data only.

- [Owner OpenAPI](openapi.json) / [viewer OpenAPI](shared-openapi.json)
- [Authentication](auth-contract.md)
- [Map activity](activity-contract.md)
- [Plate states and lookup binding](plate-state-contract.md)
- [Sharing](share-contract.md)
- [Email delivery](email-contract.md)

Regenerate exported schemas with `python scripts/export_openapi.py`. `/docs` is available on the owner service after login. The public viewer does not expose docs or schema routes. `/runtime-config.js` on each service contains a strict allowlist of nonsecret frontend settings.
