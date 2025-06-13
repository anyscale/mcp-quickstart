from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="CalculatorServer",
    host="0.0.0.0",        
    port=8000
)

@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b

if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport="streamable-http")