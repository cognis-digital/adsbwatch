"""adsbwatch — part of the Cognis Neural Suite."""
try:  # re-export the tool's public API + identity from core
    from adsbwatch.core import *  # noqa: F401,F403
except Exception:  # pragma: no cover
    pass
try:
    from adsbwatch.core import TOOL_NAME, TOOL_VERSION
except Exception:  # pragma: no cover
    TOOL_NAME = "adsbwatch"
    TOOL_VERSION = "0.3.0"
__version__ = TOOL_VERSION

try:  # human-in-the-loop decision-support layer (advisory; no effectors)
    from adsbwatch import decision  # noqa: F401
except Exception:  # pragma: no cover
    pass

try:  # native, zero-dep intel export (GeoJSON / STIX 2.1)
    from adsbwatch import intel  # noqa: F401
    from adsbwatch.intel import to_geojson, to_stix, export  # noqa: F401
except Exception:  # pragma: no cover
    pass
