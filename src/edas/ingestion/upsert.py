import pandas as pd
import psycopg2.extras as pg_extras
import logging
from typing import List

# Define a constant for batch processing size.
# This improves performance by reducing the number of database roundtrips.
BATCH_SIZE = 5000

# Initialize logger for this module.
log = logging.getLogger(__name__)

def upsert_energy_consumption(raw_conn, df: pd.DataFrame) -> int:
    """
    Performs a batch 'UPSERT' (Update or Insert) for energy consumption data.
    
    This function implements the "Incremental updates and duplicate prevention"
    requirement from Part 2 by using PostgreSQL's 'ON CONFLICT' feature.

    Args:
        raw_conn: A raw psycopg2 database connection object.
        df: The pandas DataFrame containing standardized consumption data.

    Returns:
        int: The number of records processed.
    """
    # If the DataFrame is empty, do nothing and return 0.
    if df.empty:
        log.warning("Consumption DataFrame is empty. Skipping upsert.")
        return 0

    # Convert DataFrame to a list of tuples for efficient batch insertion.
    # Select columns explicitly so the tuple order matches the INSERT column list.
    df = df[["country_code", "time_stamp", "consumption_mw"]]
    records = list(df.itertuples(index=False, name=None))
    
    # Define the parameterized SQL query for batch UPSERT.
    sql = """
        INSERT INTO energy_consumption (country_code, time_stamp, consumption_mw)
        VALUES %s
        ON CONFLICT (country_code, time_stamp) DO UPDATE
        SET consumption_mw = EXCLUDED.consumption_mw;
    """
    
    # Use a database cursor to execute the batch operation.
    with raw_conn.cursor() as cur:
        # Use psycopg2's execute_values for high-performance batch operations.
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

    # SQL query for batch UPSERT into the production table.
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

    # SQL query for batch UPSERT into the cross_border_flow table.
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