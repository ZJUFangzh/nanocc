"""Tool registry — discover and look up tools by name."""

from __future__ import annotations

from nanocc.tools.base import BaseTool


def get_all_tools() -> list[BaseTool]:
    """Return all built-in tools."""
    from nanocc.tools.agent_tool import AgentTool
    from nanocc.tools.ask_user import AskUserTool
    from nanocc.tools.bash import BashTool
    from nanocc.tools.file_edit import FileEditTool
    from nanocc.tools.file_read import FileReadTool
    from nanocc.tools.file_write import FileWriteTool
    from nanocc.tools.glob_tool import GlobTool
    from nanocc.tools.grep_tool import GrepTool
    from nanocc.tools.skill_tool import SkillTool
    from nanocc.tools.web_fetch import WebFetchTool
    from nanocc.assistant.brief import BriefTool, SleepTool

    return [
        BashTool(),
        FileReadTool(),
        FileWriteTool(),
        FileEditTool(),
        GlobTool(),
        GrepTool(),
        WebFetchTool(),
        AskUserTool(),
        AgentTool(),
        SkillTool(),
        BriefTool(),
        SleepTool(),
    ]


def find_tool(tools: list[BaseTool], name: str) -> BaseTool | None:
    """Find a tool by name."""
    for tool in tools:
        if tool.name == name:
            return tool
    return None
