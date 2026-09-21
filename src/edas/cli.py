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
    
    # Load environment variables (like DB_USER, ENTSOE_API_KEY) from .env file
    load_dotenv()

    # --- Argument Parsing ---
    p = argparse.ArgumentParser(prog="edas-ingest", description="ENTSO-E ingestion pipeline")
    # Define runtime mode
    p.add_argument(
        "--mode", 
        choices=["last_10_days", "full_2025", "custom"], 
        default="last_10_days"
    )
    # Define custom date range arguments
    p.add_argument("--start", help="YYYY-MM-DD (required if --mode custom)")
    p.add_argument("--end", help="YYYY-MM-DD (required if --mode custom)")
    # Define country list argument
    p.add_argument(
        "--countries", 
        nargs="+", 
        default=["FR", "DE"], 
        help="List of country codes (e.g., FR DE)"
    )
    args = p.parse_args()

    # --- Import Application Service ---
    # Import is placed here so that CLI help (-h) is fast 
    # and doesn't load the entire application stack.
    from edas.pipeline import run_pipeline

    # --- Argument Validation ---
    if args.mode == "custom" and (not args.start or not args.end):
        p.error("--start and --end are required when --mode=custom")

    # --- Execute Pipeline ---
    try:
        # Attempt to run the pipeline with all arguments (including custom dates)
        run_pipeline(
            mode=args.mode,
            countries=args.countries,
            start=args.start,
            end=args.end,
        )
    except TypeError:
        # Fallback: If the pipeline signature doesn't accept start/end (e.g., non-custom mode),
        # run with only the essential arguments.
        run_pipeline(mode=args.mode, countries=args.countries)

def dashboard_main():
    """
    CLI entrypoint for the Dash app (edas-dashboard).
    
    Imports and runs the Dash development server.
    """
    # Import the configured Dash app instance from the dashboard module
    from edas.dashboard.app import app
    
    # Run the Dash development server
    app.run(host="127.0.0.1", port=8050, debug=True)
