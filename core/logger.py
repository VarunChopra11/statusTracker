import logging
import sys
from datetime import datetime

class StatusFormatter(logging.Formatter):

    _STANDARD_FMT = "[%(asctime)s] %(levelname)s - %(name)s - %(message)s"
    _DATE_FMT     = "%Y-%m-%d %H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:

        if isinstance(record.msg, dict) and "product" in record.msg and "status" in record.msg:
            ts      = record.msg.get("timestamp", datetime.now().strftime(self._DATE_FMT))
            product = record.msg["product"]
            status  = record.msg["status"]
            return (
                f"[{ts}] Product: {product}\n"
                f"Status: {status}"
            )

        formatter = logging.Formatter(self._STANDARD_FMT, datefmt=self._DATE_FMT)
        return formatter.format(record)

def _build_logger() -> logging.Logger:

    log = logging.getLogger("status_tracker")

    if log.handlers:
        return log

    log.setLevel(logging.DEBUG)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(StatusFormatter())

    log.addHandler(handler)
    log.propagate = False

    return log


logger: logging.Logger = _build_logger()