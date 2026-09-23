import logging
import time
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import text

from edas.db.connection import get_engine
from edas.ingestion.entsoe_client import (
    fetch_consumption, fetch_production, fetch_flow
)
from edas.ingestion.upsert import (
    upsert_energy_consumption, upsert_energy_production, upsert_cross_border_flow
)

log = logging.getLogger(__name__)
# Logging is configured by the entry point (cli.py), not by this module.

NEIGHBORS: Dict[str, List[str]] = {
    "FR": ["BE", "DE", "ES", "CH"],
    "DE": ["NL", "BE", "FR", "CH", "AT", "CZ", "PL"],
}


def _load_countries(engine) -> Dict[str, Dict[str, str]]:
    """Helper function to load country metadata (name, zone key) from the DB."""
    sql = "SELECT country_code, country_name, zone_key FROM countries;"
    log.debug("Loading countries metadata with SQL: %s", sql)
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()
    meta = {r["country_code"]: {"name": r["country_name"], "zone": r["zone_key"]} for r in rows}
    log.info("Loaded %d countries from DB: %s", len(meta), list(meta.keys()))
    return meta


def _compute_range(mode: str):
    """
    Compute [start, end] in 'Europe/Brussels' time (hourly aligned).
    The 'end' timestamp is offset by 1 hour to avoid fetching partial (current) hour data.
    """
    now_bxl = pd.Timestamp.utcnow().tz_convert("Europe/Brussels")
    end = now_bxl.floor("h") - pd.Timedelta(hours=1)

    if mode == "last_10_days":
        start = end - pd.Timedelta(days=10)
    elif mode == "full_2025":
        start = pd.Timestamp("2025-01-01 00:00", tz="Europe/Brussels")
        end = pd.Timestamp("2025-12-31 23:00", tz="Europe/Brussels")
    else:
        raise ValueError(f"Unknown mode: {mode}")

    log.debug("Computed range for mode=%s -> start=%s, end=%s", mode, start, end)
    return start, end


def run_pipeline(
    countries: Optional[List[str]] = None,
    include_flows: bool = True,
    mode: str = "last_10_days",
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    """
    Main Application Service function to run the full ingestion pipeline.
    
    This function orchestrates the ETL process:
    1. Connects to the DB and loads metadata.
    2. Computes the time range.
    3. Loops through countries, fetching data from the ENTSO-E adapter.
    4. Saves data using the batch upsert (Repository) functions.
    5. All DB operations are performed within a single transaction.
    """
    t0 = time.perf_counter() # Start performance timer
    log.info(
        "Pipeline start | mode=%s | include_flows=%s | requested_countries=%s",
        mode, include_flows, countries
    )

    try:
        engine = get_engine()
        log.info("DB engine created successfully")

        meta = _load_countries(engine)

        if not countries:
            countries = ["FR", "DE"] # Default to project requirements
            log.info("No countries provided; defaulting to %s", countries)

        missing = [c for c in countries if c not in meta]
        if missing:
            log.warning("Some requested countries are missing in metadata: %s", missing)
            countries = [c for c in countries if c in meta]
        if not countries:
            log.error("No valid countries to process after metadata check. Aborting.")
            return

        if start and end:
            start_ts = pd.Timestamp(start, tz="Europe/Brussels")
            end_ts = pd.Timestamp(end, tz="Europe/Brussels")
        elif mode == "custom":
            raise ValueError("mode='custom' requires both start and end")
        else:
            start_ts, end_ts = _compute_range(mode)
        log.info("Range resolved | mode=%s :: %s → %s", mode, start_ts, end_ts)

        # 5. Execute the ingestion within a single transaction
        with engine.begin() as sa_conn:
            # Get the raw psycopg2 connection for fast batch upserting
            raw = sa_conn.connection.driver_connection
            log.debug("Opened transaction and acquired raw DB connection")

            for cc in countries:
                zone = meta[cc]["zone"]

                log.info("Fetching consumption | country=%s | zone=%s", cc, zone)
                cons = fetch_consumption(cc, zone, start_ts, end_ts)
                n_cons = upsert_energy_consumption(raw, cons)
                log.info("Upsert consumption | country=%s | rows=%d", cc, n_cons)

                log.info("Fetching production | country=%s | zone=%s", cc, zone)
                prod = fetch_production(cc, zone, start_ts, end_ts)
                n_prod = upsert_energy_production(raw, prod)
                log.info("Upsert production | country=%s | rows=%d", cc, n_prod)

            if include_flows:
                for cc in countries:
                    from_zone = meta[cc]["zone"]
                    neighbors = NEIGHBORS.get(cc, [])
                    if not neighbors:
                        log.debug("No neighbors configured for %s; skipping flows", cc)
                        continue

                    for nb in neighbors:
                        if nb not in meta:
                            log.debug("Neighbor %s not present in metadata; skipping %s -> %s", nb, cc, nb)
                            continue

                        to_zone = meta[nb]["zone"]
                        log.info("Fetching flow | %s -> %s | zones: %s -> %s", cc, nb, from_zone, to_zone)
                        flow = fetch_flow(cc, nb, from_zone, to_zone, start_ts, end_ts)
                        n_flow = upsert_cross_border_flow(raw, flow)
                        if n_flow > 0:
                            log.info("Upsert flow | %s -> %s | rows=%d", cc, nb, n_flow)
                        else:
                            log.debug("No flow rows upserted for %s -> %s", cc, nb)
        
        # Transaction commits automatically here if 'with' block succeeds
        dt = time.perf_counter() - t0
        log.info("Pipeline finished successfully in %.2fs", dt)

    except Exception as e:
        # Transaction automatically rolls back if an exception occurs
        dt = time.perf_counter() - t0
        log.exception("Pipeline failed after %.2fs: %s", dt, e)
        # Re-raise so callers (like CLI or CI) can fail properly
        raise