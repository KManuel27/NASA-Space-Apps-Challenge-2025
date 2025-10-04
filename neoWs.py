"""
The NeoWs (Near Earth Object Web Service) API provides access to current and historical near earth asteroid data.
"""

import os
import json
import copy
import requests
from typing import Any, Dict, List

# constants
api_feed_url = "https://api.nasa.gov/neo/rest/v1/feed"
api_lookup_url_template = "https://api.nasa.gov/neo/rest/v1/neo/{id}"
default_api_key = os.environ.get("NASA_API_KEY", "DEMO_KEY")  # SET ENV VAR NASA_API_KEY if you have one
request_timeout = 10  # seconds

def _request_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """http get and return parsed json"""
    r = requests.get(url, params=params, timeout=request_timeout)
    r.raise_for_status()
    return r.json()


def _neo_feed(start_date: str, end_date: str) -> Dict[str, Any]:
    """get feed of near earth objects between start_date and end_date"""
    params = {"start_date": start_date, "end_date": end_date, "api_key": default_api_key}
    return _request_json(api_feed_url, params)


def _neo_lookup(asteroid_id: str) -> Dict[str, Any]:
    """lookup detailed asteroid record by id (no caching)"""
    url = api_lookup_url_template.format(id=asteroid_id)
    return _request_json(url, {"api_key": default_api_key})


def _min_miss_km(item: Dict[str, Any]) -> float:
    """compute smallest miss distance in kilometers for an object's approaches"""
    approaches = item.get("close_approach_data", [])
    min_km = float("inf")
    for a in approaches:
        try:
            km_str = a.get("miss_distance", {}).get("kilometers")
            if km_str is None:
                continue
            km = float(km_str)
            if km < min_km:
                min_km = km
        except (TypeError, ValueError):
            continue
    return min_km


def _sanitise_approach(approach: Dict[str, Any]) -> None:
    """remove non-metric fields from a close_approach_data entry."""
    miss = approach.get("miss_distance")
    if isinstance(miss, dict):
        miss.pop("lunar", None)
        miss.pop("miles", None)

    rel = approach.get("relative_velocity")
    if isinstance(rel, dict):
        rel.pop("miles_per_hour", None)
        rel.pop("miles_per_hr", None)


def _simplify_estimated_diameter(obj: Dict[str, Any]) -> None:
    """restrict estimated_diameter to only the kilometers entry."""
    km = obj.get("estimated_diameter", {}).get("kilometers")
    if km is not None:
        obj["estimated_diameter"] = {"kilometers": km}
    else:
        obj.pop("estimated_diameter", None)


def _simplify_object_lookup(obj_lookup: Dict[str, Any], approaches_from_feed: List[Dict[str, Any]]) -> Dict[str, Any]:
    """prepare a version of the full lookup object constrained to the feed approaches."""
    # make a shallow copy of the lookup data then replace approach list
    obj_copy = copy.deepcopy(obj_lookup)
    obj_copy["close_approach_data"] = approaches_from_feed or []

    # sanitise each approach entry in-place
    for approach in obj_copy.get("close_approach_data", []):
        _sanitise_approach(approach)

    # keep only kilometers for estimated diameter
    _simplify_estimated_diameter(obj_copy)

    # remove top-level links if present
    obj_copy.pop("links", None)

    return obj_copy


def _filter_neo_feed(response_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """filter feed to keep only potentially hazardous asteroids and simplify fields."""
    objs: List[Dict[str, Any]] = []
    data = response_json or {}

    # iterate dates in feed; structure: {"near_earth_objects": { "YYYY-MM-DD": [obj, ...], ... }}
    for date, objects_on_date in data.get("near_earth_objects", {}).items():
        for obj in objects_on_date:
            # only include those flagged hazardous in the feed summary
            if not obj.get("is_potentially_hazardous_asteroid"):
                continue

            neo_id = obj.get("neo_reference_id")
            if not neo_id:
                continue

            # lookup full object details (no cache) and then constrain approaches to those in this feed date
            obj_lookup = _neo_lookup(neo_id)
            approaches_from_feed = obj.get("close_approach_data", [])
            simplified = _simplify_object_lookup(obj_lookup, approaches_from_feed)

            objs.append(simplified)

    # sort by nearest miss (km) so closest approaches appear first
    objs.sort(key=_min_miss_km)
    return objs


def get_hazardous_asteroids(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Public helper: fetch feed and return filtered hazardous asteroid objects.

    Returns a list of simplified lookup objects (same shape as produced by
    _filter_neo_feed).
    """
    response = _neo_feed(start_date, end_date)
    return _filter_neo_feed(response)


def lookup_asteroid(asteroid_id: str) -> Dict[str, Any]:
    """Public helper: lookup a single asteroid by id using NeoWs lookup endpoint."""
    return _neo_lookup(asteroid_id)


if __name__ == "__main__":
    output_file = "meteor.json"
    start_date = "2025-10-01"
    end_date = "2025-10-08"

    feed = _neo_feed(start_date, end_date)
    filtered = _filter_neo_feed(feed)
    with open(output_file, "w") as f:
        json.dump(filtered, f, indent=4)
