import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logging(level: str = "INFO") -> None:
    """
    Configures the root logger with a console handler and a rotating file
    handler. No-op if the root logger already has handlers (safe to call
    from multiple entry points). Writes to 'logs/app.log', relative to the
    current working directory.
    """
    logger = logging.getLogger()
    if logger.handlers:
        return

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt)

    stream_h = logging.StreamHandler()
    stream_h.setFormatter(formatter)
    logger.addHandler(stream_h)

    log_file_path = "logs/app.log"

    log_directory = os.path.dirname(log_file_path)

    if not os.path.exists(log_directory):
        try:
            os.makedirs(log_directory)
        except OSError as e:
            # Handle potential race condition or permission error
            logger.error(f"Could not create log directory: {e}")
            return # Do not add file handler if dir creation fails

    file_h = RotatingFileHandler(log_file_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_h.setFormatter(formatter)
    logger.addHandler(file_h)