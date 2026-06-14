"""adsbwatch — part of the Cognis Neural Suite."""
# Re-export the tool's public API + identity from core.
# Using explicit imports (not *) so that import errors surface clearly rather
# than being silently swallowed.
from adsbwatch.core import (  # noqa: F401
    TOOL_NAME,
    TOOL_VERSION,
    SQUAWK_MEANINGS,
    EARTH_RADIUS_NM,
    Observation,
    Anomaly,
    AnalysisResult,
    parse_records,
    parse_csv,
    haversine_nm,
    analyze,
    scan,
    to_json,
)

__version__ = TOOL_VERSION
