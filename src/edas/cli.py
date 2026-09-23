import argparse
from dotenv import load_dotenv
from edas.logging_config import setup_logging

def ingest_main():
    """
    CLI entrypoint for the data ingestion pipeline (edas-ingest).
    
    Parses command-line arguments for mode, date range, and countries,
    then calls the main pipeline orchestrator.
    """
    setup_logging("INFO")

    load_dotenv()

    p = argparse.ArgumentParser(prog="edas-ingest", description="ENTSO-E ingestion pipeline")
    p.add_argument(
        "--mode",
        choices=["last_10_days", "full_2025", "custom"],
        default="last_10_days"
    )
    p.add_argument("--start", help="YYYY-MM-DD (required if --mode custom)")
    p.add_argument("--end", help="YYYY-MM-DD (required if --mode custom)")
    p.add_argument(
        "--countries",
        nargs="+",
        default=["FR", "DE"],
        help="List of country codes (e.g., FR DE)"
    )
    p.add_argument(
        "--no-flows",
        action="store_true",
        help="If set, skips the ingestion of cross-border flows."
    )
    args = p.parse_args()

    # --- Import Application Service ---
    # Import is placed here so that CLI help (-h) is fast 
    # and doesn't load the entire application stack.
    from edas.pipeline import run_pipeline

    if args.mode == "custom" and (not args.start or not args.end):
        p.error("--start and --end are required when --mode=custom")

    run_pipeline(
        mode=args.mode,
        countries=args.countries,
        start=args.start,
        end=args.end,
        include_flows=(not args.no_flows),
    )

def dashboard_main():
    """
    CLI entrypoint for the Dash app (edas-dashboard).
    
    Imports and runs the Dash development server.
    """
    from edas.dashboard.app import app
    from edas.config import debug_enabled

    # Run the Dash development server (debug mode is opt-in via EDAS_DEBUG)
    app.run(host="127.0.0.1", port=8050, debug=debug_enabled())
