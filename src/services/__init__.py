"""Business logic: the LangGraph graph, orchestration and decision rules.

Nothing in this layer imports an external SDK or knows that HTTP exists. It
talks to the outside world only through the Protocols in ``models.ports``.
"""
