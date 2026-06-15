# ADSBWATCH — Roadmap

## Now (v0.2)
- Stable `scan` CLI (table / JSON), CI fail-gate, MCP server, demo scenarios.
- **Decision support (`assess`)** — the layer above the alert: triage by priority,
  correlate with local camera/RF/access-control logs, and recommend operator courses of
  action. Human-in-the-loop and advisory only — no effector/weapon interface, never
  autonomous (enforced by a scope-guard test). Use of force stays with a person.

## Next (v0.3)
- More correlation connectors (camera/NVR, RF/SDR loggers, access-control exports).
- Operator notification sinks (email/Slack/webhook) via cognis-connect — still advisory.
- Expand the rule/heuristic set; OSINT aviation monitoring content.

## Later (v1.0)
- PyPI release, plugin API, Pro tier + commercial support (licensing@cognis.digital).

Open an issue or PR to shape priorities — see [CONTRIBUTING.md](CONTRIBUTING.md).
