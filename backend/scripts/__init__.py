"""Operational scripts that are run by hand, not imported by the app.

Kept a package so they can be run as `python -m scripts.<name>` and pick up
`pytest.ini`'s `pythonpath = .` convention for importing `app.*`.
"""
