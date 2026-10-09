"""In-memory stand-ins for every port that touches the outside world (R-09).

``fake_dataset`` replaces datos.gov.co and ``fake_voice`` replaces the realtime
engines, Cartesia, the affect models, the analyst and the feedback sink. They
are simplified but honest implementations, so a test that passes here is
evidence the logic works, not just that a method was called.
"""
