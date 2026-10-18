"""BigQuery backend: schema, loader, repository, state store and setup CLI.

All SQL lives in ``schema.py`` and ``sql.py`` as plain strings so it can be reviewed, parsed with
sqlglot's BigQuery dialect in tests, printed by ``setup --dry-run`` and executed unchanged in production.
Nothing in this package runs unless ``TS_DATA_BACKEND=bigquery`` (or the setup CLI / sync button is used).
"""
