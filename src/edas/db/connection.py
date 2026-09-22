import os
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

def get_engine():
    """
    Creates and returns a SQLAlchemy engine for PostgreSQL (Database Adapter).

    This function acts as a factory, centralizing the database connection logic.
    It securely reads all configuration from environment variables.

    Raises:
        EnvironmentError: If any required database environment variable is missing.

    Returns:
        sqlalchemy.engine.Engine: The configured SQLAlchemy engine (connection pool).
    """

    required_vars = ["DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME"]

    for var in required_vars:
        if not os.getenv(var):
            raise EnvironmentError(f"Missing required environment variable: {var}")

    uri = (
        f"postgresql+psycopg2://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )

    # 'pool_pre_ping=True' checks connection validity before use, preventing stale connections.
    return create_engine(uri, pool_pre_ping=True)