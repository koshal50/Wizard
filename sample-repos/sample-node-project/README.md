# sample-node-project

A tiny Node.js HTTP service used as a fixture for the **Wizard investigation
planner**. It has no third-party dependencies — everything uses the Node.js
standard library — so it runs anywhere Node runs.

## Run

```bash
npm start
# → sample-node-project listening on http://127.0.0.1:3000
```

## Endpoints

| Method | Path      | Response                            |
| ------ | --------- | ----------------------------------- |
| GET    | `/`       | `sample-node-project is running`    |
| GET    | `/health` | `{ "status": "ok", "uptime": ... }` |

## Why this exists

The Wizard scans this repository, builds a manifest (detecting **Node.js** from
`package.json` and the `server.js` entry file), and then investigates two goals:

- **Verify Runtime** — probes `node --version` to confirm the runtime works.
- **Verify Dependencies** — locates and parses `package.json`.

See `docs/ARCHITECTURE.md` in the Wizard repo for the full flow.
