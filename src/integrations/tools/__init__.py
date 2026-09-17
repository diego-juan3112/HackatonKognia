from config import Settings
from integrations.tools.calculator_tool import calculator
from integrations.tools.web_search_tool import get_web_search_tool


def default_toolset(settings: Settings) -> list:
    """Assemble the agent's tool list.

    Starts minimal (the calculator needs no API key, so it works offline) and
    adds web search only when TAVILY_API_KEY is configured. Challenge-specific
    tools get added here.
    """
    tools = [calculator]

    web_search = get_web_search_tool(settings)
    if web_search is not None:
        tools.append(web_search)

    return tools
