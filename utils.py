import logging

from cachetools import TTLCache

from config import LOG_FILENAME

# run.sh redirects stdout/stderr into this same file, so the timestamp and level
# keep these records distinguishable from raw tracebacks and library output.
logging.basicConfig(
    filename=LOG_FILENAME,
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

# These are chatty at INFO and would outpace logrotate.
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# Prayer times change once a day, so a 24h TTL is enough.
prayer_time_cache = TTLCache(maxsize=100, ttl=24 * 60 * 60)


def normalize_location(location):
    """Returns a canonical cache key so "singapore" and "Singapore " match."""
    if not location:
        return ""
    return " ".join(str(location).split()).casefold()
