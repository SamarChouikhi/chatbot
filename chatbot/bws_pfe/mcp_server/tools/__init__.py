# ============================================================
# __init__.py — Export tools MCP ARIA
# D:\bws_pfe\mcp_server\tools\__init__.py
# ============================================================

from mcp_server.tools.database import (
    list_tables,
    describe_table,
    execute_query,
)
from mcp_server.tools.sensors import (
    realtime_data,
    thl_analysis,
)
from mcp_server.tools.alerts import (
    alerts_summary,
)
from mcp_server.tools.utils import (
    count_rows,
    search_in_table,
    database_summary,
)
from mcp_server.tools.anomaly import (
    anomaly_detection,
)

ALL_TOOLS = [
    list_tables,
    describe_table,
    execute_query,
    realtime_data,
    thl_analysis,
    alerts_summary,
    count_rows,
    search_in_table,
    database_summary,
    anomaly_detection,
]

__all__ = [
    'list_tables', 'describe_table', 'execute_query',
    'realtime_data', 'thl_analysis', 'alerts_summary',
    'count_rows', 'search_in_table', 'database_summary',
    'anomaly_detection', 'ALL_TOOLS',
]