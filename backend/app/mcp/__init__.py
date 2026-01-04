"""
MCP (Model Context Protocol) Server Module

提供 FastMCP 服务器，支持 Claude Desktop、ChatGPT、Gemini 等客户端连接
"""
from .server import mcp, get_mcp_app

__all__ = ["mcp", "get_mcp_app"]
