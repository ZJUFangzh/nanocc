"""WebFetchTool — fetch and process web content."""

from __future__ import annotations

from typing import Any

from nanocc.tools.base import BaseTool
from nanocc.types import ToolResult, ToolUseContext


class WebFetchTool(BaseTool):
    name = "WebFetch"
    description = "Fetch content from a URL. Returns the page content as text."
    is_read_only = True
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch.",
            },
            "prompt": {
                "type": "string",
                "description": "What to extract from the page content.",
            },
        },
        "required": ["url"],
    }

    async def execute(
        self, input: dict[str, Any], context: ToolUseContext
    ) -> ToolResult:
        url = input.get("url", "")
        if not url:
            return ToolResult(content="Error: URL is required", is_error=True)

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "nanocc/0.1"})
                resp.raise_for_status()
                content = resp.text

            # Basic HTML to text conversion
            if "<html" in content.lower() or "<body" in content.lower():
                content = _strip_html(content)

            # Truncate
            max_chars = 50_000
            if len(content) > max_chars:
                content = content[:max_chars] + "\n... [truncated]"

            return ToolResult(content=content)
        except Exception as e:
            return ToolResult(content=f"Fetch error: {e}", is_error=True)


def _strip_html(html: str) -> str:
    """Basic HTML tag stripping."""
    import re
    # Remove script and style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Clean whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text
