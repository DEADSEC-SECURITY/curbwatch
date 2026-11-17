# Local portal simulation

`mocks/syracuse/default.js` is a local, non-forwarding HTTP stand-in with synthetic plates only. Pytest starts it automatically for portal adapter tests; Node.js is required. It verifies cookies/CSRF, multipart searches, arrays, single-ticket redirects, explicit empty results and source failures.

For an independent local server:

```sh
node postman/mocks/syracuse/default.js
PARKING_SIMULATION_URL=http://127.0.0.1:4510 python -m pytest tests/test_portal.py
```

The optional Postman simulation scaffold is in `simulations/parking-local.sim.yaml`. It routes the member under `/syracuse` when run with the Postman CLI. No live portal requests or credentials are needed by the tests. A green simulation proves behavior against these fixtures, not compatibility with every upstream response.

API contracts live in `docs/api/`, separate from these mocks.
