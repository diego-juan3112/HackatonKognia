"""
Herramienta opcional de búsqueda web usando Tavily.

Se activa sola si defines TAVILY_API_KEY en .env. Si no la tienes,
el agente simplemente arranca sin esta tool (no revienta el arranque).

Requiere: pip install langchain-tavily
"""

from config import Settings


def get_web_search_tool(settings: Settings):
    if not settings.tavily_api_key:
        return None

    try:
        from langchain_tavily import TavilySearch
    except ImportError:
        # No está instalado el paquete opcional -> seguimos sin la tool.
        return None

    return TavilySearch(max_results=5, tavily_api_key=settings.tavily_api_key)
