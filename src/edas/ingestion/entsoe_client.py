# Import necessary logging and typing utilities.
import logging
from typing import List
# Import the core data manipulation library (pandas) and the ENTSO-E client library.
import pandas as pd
from entsoe import EntsoePandasClient

# Import project-specific configuration constants.
# ENTSOE_API_KEY is sensitive data handled via config.
from edas.config import ENTSOE_API_KEY, TZ_EUROPE


# Initialize logger for this module (good practice for debugging/monitoring in CI/CD).
log = logging.getLogger(__name__)

# Initialize the Entsoe client with the API key loaded from configuration.
client = EntsoePandasClient(api_key=ENTSOE_API_KEY)


def to_utc_naive(series: pd.Series, tz: str = TZ_EUROPE) -> pd.Series:
    """
    Converts a pandas Series of timestamps to UTC naive format.

    Handles mixed timezones: if tz-aware, converts to UTC and removes timezone info (naive);
    if tz-naive, localizes to the specified default timezone (e.g., Europe/Brussels)
    before converting to UTC naive.

    Args:
        series: The pandas Series containing timestamps.
        tz: The default timezone to assume for naive timestamps.
    Returns:
        pd.Series: The converted Series in UTC naive format.
    """
    s = pd.to_datetime(series, errors="coerce")

    # Check if the Series is timezone-aware
    if getattr(s.dtype, "tz", None) is not None:
        # If tz-aware, convert directly to UTC and then remove timezone information (naive)
        return s.dt.tz_convert("UTC").dt.tz_localize(None)

    # If tz-naive, localize first (assuming default timezone), then convert to UTC naive
    return s.dt.tz_localize(tz).dt.tz_convert("UTC").dt.tz_localize(None)


def _flatten_columns(cols) -> List[str]:
    """
    Flattens MultiIndex column headers from ENTSOE API response into a single string list.

    This handles nested column names (e.g., ('Actual Consumption', 'Total')).

    Args:
        cols: The DataFrame columns (can be a standard Index or MultiIndex).
    Returns:
        List[str]: A list of flattened, human-readable column names.
    """
    if isinstance(cols, pd.MultiIndex):
        out = []
        for tup in cols.tolist():
            # Join non-empty parts of the tuple with ' | '
            parts = [str(x) for x in tup if (x is not None and str(x) != "")]
            out.append(" | ".join(parts) if parts else "UNKNOWN")
        return out
    # Return as-is if not a MultiIndex
    return [str(c) for c in cols]


def fetch_consumption(country_code: str, zone_key: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """
    Fetches electricity consumption (load) data for a given country and time range.

    Args:
        country_code: The 2-letter ISO country code (e.g., 'FR').
        zone_key: The ENTSO-E zone key.
        start: The start timestamp for the query.
        end: The end timestamp for the query.
    Returns:
        pd.DataFrame: DataFrame containing consumption data standardized to UTC naive format.
    """
    log.info("Load consumption %s (%s) %s → %s", country_code, zone_key, start, end)
    
    # Query load data using the Entsoe client
    s = client.query_load(zone_key, start=start, end=end)
    
    # Handle cases where no data is returned or the series is empty
    if s is None or s.empty:
        # Return an empty DataFrame with expected columns (standard output format)
        return pd.DataFrame(columns=["country_code", "time_stamp", "consumption_mw"])
    
    # Convert Series index (timestamp) to a column
    df = s.reset_index()
    df.columns = ["time_stamp", "consumption_mw"]
    
    # Standardize timestamps to UTC naive format
    df["time_stamp"] = to_utc_naive(df["time_stamp"])
    df["country_code"] = country_code
    
    # Return standard columns for ingestion
    return df[["country_code", "time_stamp", "consumption_mw"]]


def fetch_production(country_code: str, zone_key: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """
    Fetches electricity production (generation) data by source type.

    Args:
        country_code: The 2-letter ISO country code.
        zone_key: The ENTSO-E zone key.
        start: The start timestamp for the query.
        end: The end timestamp for the query.
    Returns:
        pd.DataFrame: DataFrame containing production data by source, standardized to long format (melted).
    """
    log.info("Load generation %s (%s) %s → %s", country_code, zone_key, start, end)
    
    # Query generation data without filtering by specific Pseudo-Source Type (psr_type=None)
    df = client.query_generation(zone_key, start=start, end=end, psr_type=None)
    
    # Handle cases where no data is returned
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["country_code", "time_stamp", "source_type", "production_mw"])

    # Handle case where the response is a single Series (e.g., total generation)
    if isinstance(df, pd.Series):
        out = pd.DataFrame({
            "country_code": country_code,
            "time_stamp": to_utc_naive(df.index),
            "source_type": "TOTAL",  # Assume total generation if single series is returned
            "production_mw": df.values,
        })
        return out

    # Handling DataFrame with multiple columns (different sources)
    df = df.copy()
    
    # Standardize index name and data type
    df.index = pd.to_datetime(df.index, errors="coerce")
    df.index.name = "time_stamp"
    
    # Flatten MultiIndex columns (if present)
    df.columns = _flatten_columns(df.columns)
    df = df.reset_index()

    # Determine which columns contain production values (all except the timestamp)
    value_cols = [c for c in df.columns if c != "time_stamp"]
    
    # Melt DataFrame from wide to long format (key for database storage by source)
    df_long = pd.melt(df, id_vars=["time_stamp"], value_vars=value_cols,
                      var_name="source_type", value_name="production_mw")
    
    # Final cleanup and standardization
    df_long["time_stamp"] = to_utc_naive(df_long["time_stamp"])
    df_long["country_code"] = country_code
    df_long = df_long.dropna(subset=["production_mw"])
    
    # Return standard columns for ingestion
    return df_long[["country_code", "time_stamp", "source_type", "production_mw"]]


def fetch_flow(from_cc: str, to_cc: str, from_zone: str, to_zone: str,
               start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """
    Fetches cross-border electricity flow data between two zones/countries.

    Args:
        from_cc: The country code where flow originates.
        to_cc: The country code where flow terminates.
        from_zone: The ENTSO-E zone key for the origin.
        to_zone: The ENTSO-E zone key for the destination.
        start: The start timestamp for the query.
        end: The end timestamp for the query.
    Returns:
        pd.DataFrame: DataFrame containing flow data, standardized.
    """
    log.info("Load flow %s(%s) -> %s(%s) %s → %s", from_cc, from_zone, to_cc, to_zone, start, end)
    
    try:
        # Query cross-border flows
        s = client.query_crossborder_flows(from_zone, to_zone, start=start, end=end)
    except Exception as e:
        # Log a warning if the API call fails (e.g., due to missing data)
        log.warning("Flow API error %s->%s: %s", from_cc, to_cc, str(e))
        return pd.DataFrame(columns=["from_country_code", "to_country_code", "time_stamp", "flow_mw"])
    
    # Handle cases where no data is returned
    if s is None or s.empty:
        return pd.DataFrame(columns=["from_country_code", "to_country_code", "time_stamp", "flow_mw"])
    
    # Standardize DataFrame structure
    df = s.reset_index()
    df.columns = ["time_stamp", "flow_mw"]
    
    # Final cleanup and standardization
    df["time_stamp"] = to_utc_naive(df["time_stamp"])
    df["from_country_code"] = from_cc
    df["to_country_code"] = to_cc
    
    # Filter out missing flow values and return standard columns
    return df.dropna(subset=["flow_mw"])[["from_country_code", "to_country_code", "time_stamp", "flow_mw"]]
