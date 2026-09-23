import pandas as pd
import psycopg2.extras as pg_extras
import logging
from typing import List

BATCH_SIZE = 5000

log = logging.getLogger(__name__)

def upsert_energy_consumption(raw_conn, df: pd.DataFrame) -> int:
    """
    Performs a batch 'UPSERT' (Update or Insert) for energy consumption data.

    Idempotent via ON CONFLICT, so re-running an overlapping range is safe.

    Args:
        raw_conn: A raw psycopg2 database connection object.
        df: The pandas DataFrame containing standardized consumption data.

    Returns:
        int: The number of records processed.
    """
    if df.empty:
        log.warning("Consumption DataFrame is empty. Skipping upsert.")
        return 0

    # Select columns explicitly so the tuple order matches the INSERT column list.
    df = df[["country_code", "time_stamp", "consumption_mw"]]
    records = list(df.itertuples(index=False, name=None))

    sql = """
        INSERT INTO energy_consumption (country_code, time_stamp, consumption_mw)
        VALUES %s
        ON CONFLICT (country_code, time_stamp) DO UPDATE
        SET consumption_mw = EXCLUDED.consumption_mw;
    """

    with raw_conn.cursor() as cur:
        pg_extras.execute_values(cur, sql, records, page_size=BATCH_SIZE)
        log.info("Upserted %d consumption records.", len(records))

    return len(records)

def upsert_energy_production(raw_conn, df: pd.DataFrame) -> int:
    """
    Performs a batch 'UPSERT' for energy production data (by source).

    Uses 'ON CONFLICT' to handle duplicate records, ensuring idempotency.

    Args:
        raw_conn: A raw psycopg2 database connection object.
        df: The pandas DataFrame containing standardized production data.

    Returns:
        int: The number of records processed.
    """
    if df.empty:
        log.warning("Production DataFrame is empty. Skipping upsert.")
        return 0

    # Select columns explicitly so the tuple order matches the INSERT column list.
    df = df[["country_code", "time_stamp", "source_type", "production_mw"]]
    records = list(df.itertuples(index=False, name=None))

    sql = """
        INSERT INTO energy_production (country_code, time_stamp, source_type, production_mw)
        VALUES %s
        ON CONFLICT (country_code, time_stamp, source_type) DO UPDATE
        SET production_mw = EXCLUDED.production_mw;
    """
    
    with raw_conn.cursor() as cur:
        pg_extras.execute_values(cur, sql, records, page_size=BATCH_SIZE)
        log.info("Upserted %d production records.", len(records))
        
    return len(records)

def upsert_cross_border_flow(raw_conn, df: pd.DataFrame) -> int:
    """
    Performs a batch 'UPSERT' for cross-border flow data.

    Uses 'ON CONFLICT' on the composite primary key to ensure data integrity.

    Args:
        raw_conn: A raw psycopg2 database connection object.
        df: The pandas DataFrame containing standardized flow data.

    Returns:
        int: The number of records processed.
    """
    if df.empty:
        log.warning("Cross-border flow DataFrame is empty. Skipping upsert.")
        return 0

    # Select columns explicitly so the tuple order matches the INSERT column list.
    df = df[["from_country_code", "to_country_code", "time_stamp", "flow_mw"]]
    records = list(df.itertuples(index=False, name=None))

    sql = """
        INSERT INTO cross_border_flow (from_country_code, to_country_code, time_stamp, flow_mw)
        VALUES %s
        ON CONFLICT (from_country_code, to_country_code, time_stamp) DO UPDATE
        SET flow_mw = EXCLUDED.flow_mw;
    """
    
    with raw_conn.cursor() as cur:
        pg_extras.execute_values(cur, sql, records, page_size=BATCH_SIZE)
        log.info("Upserted %d cross-border flow records.", len(records))
        
    return len(records)