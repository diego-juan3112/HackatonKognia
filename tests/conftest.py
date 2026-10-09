"""Shared test setup.

The default suite runs offline (R-16): the doubles in ``tests/doubles/`` stand in
for datos.gov.co, the voice engines, Cartesia and the affect models. Each test
module builds what it needs; live probes against the real API live in
``tests/live/`` and are skipped unless ``KOGNIA_LIVE=1``.
"""
