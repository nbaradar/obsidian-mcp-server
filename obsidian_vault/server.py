"""FastMCP server initialization and tool registration."""

import logging
from mcp.server.fastmcp import FastMCP

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("obsidian_vault")

# Tool modules are imported in __init__.py to register all @mcp.tool() decorators


def run_server():
    """Start the MCP server with stdio transport."""
    logger.info("Starting Obsidian MCP Server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run_server()
