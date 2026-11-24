"""Console entry point for the MCP connector exe (stdio needs a console; the main exe has none)."""
import sys

from datawatch.mcp_server import main

if __name__ == "__main__":
    sys.exit(main())
