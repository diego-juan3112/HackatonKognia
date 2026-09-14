from agent_core.infrastructure.tools.calculator_tool import calculator
from agent_core.infrastructure.tools.web_search_tool import get_web_search_tool


def default_toolset(settings) -> list:
    """
    Arma la lista de herramientas del agente.

    Empieza mínima (calculadora, que funciona sin ninguna API key,
    ideal para probar el agente offline hoy mismo) y suma la búsqueda
    web solo si hay TAVILY_API_KEY configurada. Agrega aquí las
    herramientas propias del reto (ej. una que llame a tu API interna,
    a una base de datos, etc.).
    """
    tools = [calculator]

    web_search = get_web_search_tool(settings)
    if web_search is not None:
        tools.append(web_search)

    return tools
