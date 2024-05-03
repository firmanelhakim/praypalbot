from cachetools import TTLCache

import logging

from config import LOG_FILENAME

# Configure logging
logging.basicConfig(filename=LOG_FILENAME, level=logging.ERROR)

# Configure caching
prayer_time_cache = TTLCache(
    maxsize=100,  # Adjust max size if needed
    ttl=24 * 60 * 60,  # Cache for 24 hours (24 hours * 60 minutes * 60 seconds)
)
