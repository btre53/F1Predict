"""Offline ETL: FastF1 + Jolpica -> normalized Polars frames -> Parquet/Postgres.

Golden rule (docs/science/03): the data APIs are slow and rate-limited. Run this
as an offline batch; the web app reads only the derived artifacts, never the APIs.
"""
