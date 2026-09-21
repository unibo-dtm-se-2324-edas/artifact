import pandas as pd
from typing import Iterable, Tuple, Callable
from sqlalchemy.engine import Engine

# Define a Type Hint for the engine factory.
# This pattern (Dependency Injection) makes testing easier
# as we can pass a mock engine factory.
EngineFactory = Callable[[], Engine]


def _as_tuple(countries: Iterable[str]) -> Tuple[str, ...]:
    """Helper function to ensure the country list is a tuple for SQL queries."""
    return tuple(countries) if not isinstance(countries, tuple) else countries


def consumption_vs_production(
    engine_factory: EngineFactory,
    countries: Iterable[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    """
    Fetches aggregated consumption and production time-series data.
    Used for the main 'Consumption vs. Production' visual.
    """
    countries_t = _as_tuple(countries)
    with engine_factory().connect() as conn:
        # Query 1: Get total consumption aggregated by timestamp
        cons = pd.read_sql(
            """
            SELECT time_stamp, SUM(consumption_mw) AS consumption_mw
            FROM energy_consumption
            WHERE country_code = ANY(%(countries)s)
              AND time_stamp BETWEEN %(start)s AND %(end)s
            GROUP BY time_stamp
            ORDER BY time_stamp
            """,
            conn,
            params={"countries": list(countries_t), "start": start, "end": end},
        )
        # Query 2: Get total production aggregated by timestamp
        prod = pd.read_sql(
            """
            SELECT time_stamp, SUM(production_mw) AS production_mw
            FROM energy_production
            WHERE country_code = ANY(%(countries)s)
              AND time_stamp BETWEEN %(start)s AND %(end)s
            GROUP BY time_stamp
            ORDER BY time_stamp
            """,
            conn,
            params={"countries": list(countries_t), "start": start, "end": end},
        )
    # Merge consumption and production data on the timestamp
    df = pd.merge(cons, prod, on="time_stamp", how="outer").sort_values("time_stamp")
    return df


def kpis(
    engine_factory: EngineFactory,
    countries: Iterable[str],
    start: str,
    end: str,
) -> dict:
    """
    Calculates all major Key Performance Indicators (KPIs) for the dashboard.
    (Total Consumption, Average Consumption, Total Production, Energy Mix, Net Balance).
    """
    countries_t = _as_tuple(countries)
    with engine_factory().connect() as conn:
        # Fetch raw consumption time-series for averaging
        cons = pd.read_sql(
            """
            SELECT time_stamp, SUM(consumption_mw) AS consumption_mw
            FROM energy_consumption
            WHERE country_code = ANY(%(countries)s)
              AND time_stamp BETWEEN %(start)s AND %(end)s
            GROUP BY time_stamp
            """,
            conn,
            params={"countries": list(countries_t), "start": start, "end": end},
        )
        # Fetch raw production time-series for total
        prod = pd.read_sql(
            """
            SELECT time_stamp, SUM(production_mw) AS production_mw
            FROM energy_production
            WHERE country_code = ANY(%(countries)s)
              AND time_stamp BETWEEN %(start)s AND %(end)s
            GROUP BY time_stamp
            """,
            conn,
            params={"countries": list(countries_t), "start": start, "end": end},
        )
        # Fetch production aggregated by source type for the energy mix pie chart
        mix = pd.read_sql(
            """
            SELECT source_type, SUM(production_mw) AS production_mw
            FROM energy_production
            WHERE country_code = ANY(%(countries)s)
              AND time_stamp BETWEEN %(start)s AND %(end)s
            GROUP BY source_type
            """,
            conn,
            params={"countries": list(countries_t), "start": start, "end": end},
        )
        # Fetch total aggregated cross-border flow (Export)
        flows = pd.read_sql(
            """
            SELECT SUM(flow_mw) AS flow_mw
            FROM cross_border_flow
            WHERE from_country_code = ANY(%(countries)s)
              AND time_stamp BETWEEN %(start)s AND %(end)s
            """,
            conn,
            params={"countries": list(countries_t), "start": start, "end": end},
        )

    # Calculate Total Consumption and Production
    total_cons = cons["consumption_mw"].sum() if not cons.empty else 0.0
    total_prod = prod["production_mw"].sum() if not prod.empty else 0.0

    # Calculate Average Consumption (Daily, Weekly, Monthly)
    if not cons.empty:
        cons["day"] = pd.to_datetime(cons["time_stamp"]).dt.to_period("D")
        cons["week"] = pd.to_datetime(cons["time_stamp"]).dt.to_period("W")
        cons["month"] = pd.to_datetime(cons["time_stamp"]).dt.to_period("M")
        avg_daily = cons.groupby("day")["consumption_mw"].sum().mean()
        avg_weekly = cons.groupby("week")["consumption_mw"].sum().mean()
        avg_monthly = cons.groupby("month")["consumption_mw"].sum().mean()
    else:
        avg_daily = avg_weekly = avg_monthly = 0.0

    # Calculate Energy Mix Percentages
    if not mix.empty and mix["production_mw"].sum() > 0:
        mix["percent"] = (mix["production_mw"] / mix["production_mw"].sum()) * 100.0
    else:
        mix["percent"] = 0.0

    # Calculate Net Balance (Total Exports)
    net_balance = float(flows.iloc[0, 0]) if not flows.empty else 0.0

    # Return all KPIs as a dictionary
    return {
        "total_consumption": float(total_cons),
        "avg_daily_consumption": float(avg_daily),
        "avg_weekly_consumption": float(avg_weekly),
        "avg_monthly_consumption": float(avg_monthly),
        "total_production": float(total_prod),
        "energy_mix": mix,  # DataFrame for the pie chart
        "net_balance": float(net_balance),
    }


def production_mix(
    engine_factory: EngineFactory,
    countries: Iterable[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    """
    Fetches production data aggregated by time AND source.
    Used for the 'Stacked Area: Production Mix' visual.
    """
    countries_t = _as_tuple(countries)
    with engine_factory().connect() as conn:
        df = pd.read_sql(
            """
            SELECT time_stamp, source_type, SUM(production_mw) AS production_mw
            FROM energy_production
            WHERE country_code = ANY(%(countries)s)
              AND time_stamp BETWEEN %(start)s AND %(end)s
            GROUP BY time_stamp, source_type
            ORDER BY time_stamp
            """,
            conn,
            params={"countries": list(countries_t), "start": start, "end": end},
        )
    return df


def crossborder_flows(
    engine_factory: EngineFactory,
    countries: Iterable[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    """
    Fetches cross-border flow data aggregated by time and direction.
    Used for the 'Bar Chart: Net Flows by Country' visual.
    """
    countries_t = _as_tuple(countries)
    with engine_factory().connect() as conn:
        df = pd.read_sql(
            """
            SELECT from_country_code, to_country_code, time_stamp, SUM(flow_mw) AS flow_mw
            FROM cross_border_flow
            WHERE from_country_code = ANY(%(countries)s)
              AND time_stamp BETWEEN %(start)s AND %(end)s
            GROUP BY from_country_code, to_country_code, time_stamp
            ORDER BY time_stamp
            """,
            conn,
            params={"countries": list(countries_t), "start": start, "end": end},
        )
    return df


def hourly_consumption(
    engine_factory: EngineFactory,
    countries: Iterable[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    """
    Fetches aggregated consumption data and enriches it with hour and day.
    Used for the 'Heatmap: Hourly Consumption Patterns' visual.
    """
    countries_t = _as_tuple(countries)
    with engine_factory().connect() as conn:
        df = pd.read_sql(
            """
            SELECT time_stamp, SUM(consumption_mw) AS consumption_mw
            FROM energy_consumption
            WHERE country_code = ANY(%(countries)s)
              AND time_stamp BETWEEN %(start)s AND %(end)s
            GROUP BY time_stamp
            ORDER BY time_stamp
            """,
            conn,
            params={"countries": list(countries_t), "start": start, "end": end},
        )
    # Enrich data with temporal features needed for the heatmap
    df["hour"] = pd.to_datetime(df["time_stamp"]).dt.hour
    df["day"] = pd.to_datetime(df["time_stamp"]).dt.day_name()
    return df


def daily_summary(
    engine_factory: EngineFactory,
    countries: Iterable[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    """
    Fetches a daily summary of consumption, production, and net balance.
    Used for the 'Table: Daily Consumption & Production' visual.
    """
    countries_t = _as_tuple(countries)
    with engine_factory().connect() as conn:
        df = pd.read_sql(
            """
            SELECT
                date_trunc('day', c.time_stamp) AS day,
                SUM(c.consumption_mw) AS total_consumption,
                SUM(p.production_mw) AS total_production,
                SUM(p.production_mw) - SUM(c.consumption_mw) AS net_balance
            FROM energy_consumption c
            JOIN (
                -- Pre-aggregate to (country_code, time_stamp) so the join
                -- does not fan out consumption rows per source_type.
                SELECT country_code, time_stamp, SUM(production_mw) AS production_mw
                FROM energy_production
                GROUP BY country_code, time_stamp
            ) p
              ON c.time_stamp = p.time_stamp AND c.country_code = p.country_code
            WHERE c.country_code = ANY(%(countries)s)
              AND c.time_stamp BETWEEN %(start)s AND %(end)s
            GROUP BY day
            ORDER BY day
            """,
            conn,
            params={"countries": list(countries_t), "start": start, "end": end},
        )
    return df


def flow_table(
    engine_factory: EngineFactory,
    countries: Iterable[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    """
    Fetches raw cross-border flow data for the filterable table.
    """
    countries_t = _as_tuple(countries)
    with engine_factory().connect() as conn:
        df = pd.read_sql(
            """
            SELECT from_country_code, to_country_code, time_stamp, flow_mw
            FROM cross_border_flow
            WHERE from_country_code = ANY(%(countries)s)
              AND time_stamp BETWEEN %(start)s AND %(end)s
            ORDER BY time_stamp
            """,
            conn,
            params={"countries": list(countries_t), "start": start, "end": end},
        )
    return df