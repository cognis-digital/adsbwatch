"""ADSBWATCH MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from adsbwatch.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-adsbwatch[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-adsbwatch[mcp]'")
        return 1
    app = FastMCP("adsbwatch")

    @app.tool()
    def adsbwatch_scan(target: str) -> str:
        """Analyze an ADS-B feed/CSV for anomalies: callsign spoofing, squawk 7500/7600/7700, and unusual loiter patterns.. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
