from json import JSONDecodeError
from requests.exceptions import RequestException

import requests

from credentials import MUSLIMSALAT_API_KEY
from utils import prayer_time_cache


def get_prayer_times(location):
    """
    Fetches prayer times and timezone information for the given location,
    using caching for improved performance.

    Args:
        location (str): The user's location (e.g., "Singapore").

    Returns:
        dict or str: A dictionary containing prayer times and timezone data
                    if successful, or an error message string if an error occurred.
    """
    generic_error_message = (
        "Encountered an error while retrieving data. Please try again later."
    )

    # Check cache for existing data
    cached_data = prayer_time_cache.get(location)
    if cached_data:
        return cached_data

    try:
        response = requests.get(
            f"https://muslimsalat.com/{location}/weekly.json?key={MUSLIMSALAT_API_KEY}"
        )
        response.raise_for_status()  # Raise exception for non-200 status codes

        # Check for successful response based on API structure
        if response.json()["status_valid"] != 1 or response.json()["status_code"] != 1:
            api_error = response.json().get("status_error", {}).get("invalid_query")
            print(f"API error for location {location}: {api_error}")

            # Directly return the invalid_query if it exists
            if api_error:
                return api_error  # Return the error message itself

        prayer_times = response.json()["items"]
        timezone_offset = response.json()["timezone"]

        # Cache the successful response
        prayer_time_cache[location] = {
            "prayer_times": prayer_times,
            "timezone_offset": timezone_offset,
        }

        return {
            "prayer_times": prayer_times,
            "timezone_offset": timezone_offset,
        }
    except RequestException as e:
        print(f"Error getting prayer times for location {location}: {e}")
        # Consider providing a more specific error message to the user here
        return generic_error_message
    except JSONDecodeError as e:
        print(f"Error decoding JSON response for location {location}: {e}")
        return generic_error_message
