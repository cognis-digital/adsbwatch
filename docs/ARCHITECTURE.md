# ADSBWATCH — Architecture

> Analyze an ADS-B feed/CSV for anomalies: callsign spoofing, squawk 7500/7600/7700, and unusual loiter patterns.

```
input ──▶ collect ──▶ rules/analyzers ──▶ score ──▶ findings ──▶ table · json
                              │                          │
                         (this repo)                 MCP tool (agents)
```

- **collect** normalizes the target (file/dir/API) into records.
- **rules/analyzers** apply the heuristics shipped in `adsbwatch/core.py`.
- **score** ranks by severity.
- **MCP server** (`adsbwatch mcp`) exposes `scan` for Cognis.Studio agents.

Extend by adding a rule + a test + a `demos/NN-*/SCENARIO.md`. See [CONTRIBUTING.md](../CONTRIBUTING.md).
