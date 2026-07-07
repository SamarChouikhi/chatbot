import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from mcp.server.fastmcp import FastMCP
from mcp_server.config  import MCP_SERVER, print_config

from mcp_server.tools.database import list_tables, describe_table, execute_query
from mcp_server.tools.sensors  import (
    realtime_data, thl_analysis,
    wm_analysis, energy_analysis, gm_analysis, fuel_analysis,
)
from mcp_server.tools.alerts  import alerts_summary
from mcp_server.tools.utils   import count_rows, search_in_table, database_summary
from mcp_server.tools.anomaly      import anomaly_detection
from mcp_server.tools.predictions  import get_upcoming_predictions
from mcp_server.tools.ad_analysis  import ad_analysis
from mcp_server.tools.reco_tool    import get_recommendations

print_config()

mcp = FastMCP(name=MCP_SERVER['name'])

mcp.tool()(list_tables)
mcp.tool()(describe_table)
mcp.tool()(execute_query)
mcp.tool()(realtime_data)
mcp.tool()(thl_analysis)
mcp.tool()(wm_analysis)
mcp.tool()(energy_analysis)
mcp.tool()(gm_analysis)
mcp.tool()(fuel_analysis)
mcp.tool()(alerts_summary)
mcp.tool()(count_rows)
mcp.tool()(search_in_table)
mcp.tool()(database_summary)
mcp.tool()(anomaly_detection)
mcp.tool()(get_upcoming_predictions)
mcp.tool()(ad_analysis)
mcp.tool()(get_recommendations)

if __name__ == '__main__':
    print(f'\n  URL : http://localhost:{MCP_SERVER["port"]}/sse\n')
    mcp.run(transport='sse')
