"""
Capa de dominio (arquitectura hexagonal).

Aquí NO hay imports de LangGraph, LangChain, Azure ni FastAPI.
Solo se define el "contrato" (puerto) que el resto de capas deben
cumplir. Esto es lo que te permite:

  1. Cambiar de proveedor de modelo (OpenAI <-> Azure OpenAI) sin
     tocar la lógica del agente.
  2. Agregar/quitar herramientas sin tocar el grafo.
  3. Testear el agente con un modelo falso (fake LLM), sin llamar
     a ninguna API real.

`LLMPort` no se implementa como clase propia porque LangChain ya
expone una interfaz estable (`BaseChatModel`) que cumple este rol;
la mantenemos documentada aquí como el "puerto" oficial del proyecto
para que quede explícito en la arquitectura.
"""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

# Puerto de modelo de lenguaje: cualquier adaptador en `infrastructure/`
# debe devolver un objeto que cumpla esta interfaz.
LLMPort = BaseChatModel

# Puerto de herramienta: cualquier tool que el agente pueda usar.
ToolPort = BaseTool
