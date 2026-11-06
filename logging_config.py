import logging
import sys


def setup_logging(debug=False):
    """
    Configure logging for the health check tool.
    Logs go to console and to check.log in the current directory.
    """

    level = logging.DEBUG if debug else logging.INFO

    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    formatter = logging.Formatter(log_format, datefmt=date_format)

    # Console output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # File output
    file_handler = logging.FileHandler("check.log")
    file_handler.setFormatter(formatter)

    logging.basicConfig(
        level=level,
#        handlers=[console_handler, file_handler],
        handlers=[file_handler],
    )

    logging.getLogger("paramiko").setLevel(logging.INFO)

    # reduce noisy libraries if any appear
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("paramiko.transport").setLevel(logging.INFO)
    logging.getLogger("paramiko.packet").setLevel(logging.WARNING)
