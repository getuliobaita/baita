"""Conftest raiz.

Deliberadamente vazio de fixtures de banco: os testes em tests/unit/ nao
precisam de Postgres e nao devem ser bloqueados por ele. As fixtures de
banco (test_engine, limpeza entre testes) vivem em tests/integration/conftest.py,
escopadas so pra quem realmente precisa de um Postgres real.
"""
