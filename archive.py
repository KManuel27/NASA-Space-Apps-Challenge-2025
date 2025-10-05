"""
It uses the API from NASA's Near Earth Object Web Service (NeoWs) to fetch and process data about asteroids. And
stores them in a database for later retrieval.
"""

import sqlite3
import os
import json
import copy
import requests
import time
from datetime import datetime
from typing import Any, Dict, List


# constants
api_browse_url = "https://api.nasa.gov/neo/rest/v1/neo/browse"
default_api_key = os.environ.get("NASA_API_KEY", "DEMO_KEY")  #
request_timeout = 10  # seconds
database_file = "asteroids.db"
PAGE_SIZE = 20  # fixed page size (do not change unless you know what you're doing)
START_PAGE = 950  # change this constant to resume from a specific page (1-indexed)
RETRIES = 3  # number of attempts for HTTP requests
BACKOFF_FACTOR = 1.0  # backoff multiplier in seconds
RATE_LIMIT_SLEEP = 0.12  # seconds to sleep between requests to avoid hammering the API


def _request_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """http get and return parsed json (single attempt). Use callers' retry wrapper."""
    r = requests.get(url, params=params, timeout=request_timeout)
    r.raise_for_status()
    return r.json()


def _request_json_with_retries(url: str, params: Dict[str, Any], attempts: int = RETRIES) -> Dict[str, Any]:
    """Make an HTTP GET with a small retry/backoff loop. Raises the last exception on failure.

    Also sleeps a short amount after a successful request to apply a lightweight rate limit.
    """
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            res = _request_json(url, params)
            # polite small sleep after a successful request
            time.sleep(RATE_LIMIT_SLEEP)
            return res
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts:
                # give up
                raise
            # backoff sleep before next attempt
            backoff = BACKOFF_FACTOR * attempt
            time.sleep(backoff)
    # if somehow we exit loop without returning, raise
    if last_exc:
        raise last_exc
    raise RuntimeError("_request_json_with_retries failed without exception")


def _neo_browse(page: int) -> Dict[str, Any]:
    """get a page of near earth objects"""
    params = {"page": page, "size": PAGE_SIZE, "api_key": default_api_key}
    return _request_json_with_retries(api_browse_url, params)


api_lookup_url_template = "https://api.nasa.gov/neo/rest/v1/neo/{id}"


def _neo_lookup(asteroid_id: str) -> Dict[str, Any]:
    """lookup detailed asteroid record by id (no caching)"""
    url = api_lookup_url_template.format(id=asteroid_id)
    return _request_json_with_retries(url, {"api_key": default_api_key})


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


def _simplify_object_lookup(obj_lookup: Dict[str, Any], approaches_from_browse: List[Dict[str, Any]]) -> Dict[str, Any]:
    """prepare a version of the full lookup object constrained to the browse approaches.

    This mirrors the behaviour in `neoWs.py` and produces objects similar to `meteor.json`.
    """
    obj_copy = copy.deepcopy(obj_lookup)
    obj_copy["close_approach_data"] = approaches_from_browse or []

    for approach in obj_copy.get("close_approach_data", []):
        _sanitise_approach(approach)

    _simplify_estimated_diameter(obj_copy)

    # remove top-level links if present
    obj_copy.pop("links", None)

    return obj_copy


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


def _create_db(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS asteroids (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            inserted_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _insert_asteroid(conn: sqlite3.Connection, obj: Dict[str, Any]) -> int:
    """Insert simplified asteroid object into DB using INSERT OR IGNORE.

    Returns 1 if inserted, 0 if ignored.
    """
    aid = obj.get("id") or obj.get("neo_reference_id")
    if not aid:
        return 0
    data_text = json.dumps(obj, ensure_ascii=False)
    cur = conn.cursor()
    before = conn.total_changes
    cur.execute(
        "INSERT OR IGNORE INTO asteroids(id, data, inserted_at) VALUES (?, ?, ?)",
        (str(aid), data_text, datetime.utcnow().isoformat() + "Z"),
    )
    conn.commit()
    after = conn.total_changes
    return 1 if (after - before) > 0 else 0


def run(start_page: int = START_PAGE) -> None:
    """Run a full crawl of the browse endpoint starting from `start_page`.

    The function will iterate pages (size=PAGE_SIZE) and store simplified lookup
    objects into the sqlite database. Progress is printed as pages complete with
    elapsed time. If interrupted, it can be restarted using the same START_PAGE
    and already-stored asteroids will be skipped due to INSERT OR IGNORE.
    """
    conn = sqlite3.connect(database_file, timeout=30)
    _create_db(conn)

    page = int(start_page)
    start_time = time.time()

    # fetch the first page to learn total_pages
    try:
        first = _neo_browse(page)
    except Exception as exc:
        print(f"Failed to fetch page {page}: {exc}")
        conn.close()
        return

    page_info = first.get("page") or {}
    total_pages = page_info.get("total_pages")
    if total_pages is None:
        # fallback: try to continue until no objects returned
        total_pages = page

    # If browse returned objects, process page; otherwise we'll increment until we hit empty
    while True:
        try:
            resp = _neo_browse(page)
        except Exception as exc:
            print(f"Request failed for page {page}: {exc}")
            break

        objects = resp.get("near_earth_objects") or []
        if not objects:
            print(f"No objects on page {page}, stopping.")
            break

        inserted_this_page = 0
        for obj in objects:
            neo_id = obj.get("neo_reference_id") or obj.get("id")
            if not neo_id:
                continue
            try:
                lookup = _neo_lookup(neo_id)
            except Exception as exc:
                print(f"Failed lookup for {neo_id} on page {page}: {exc}")
                continue

            approaches_from_browse = obj.get("close_approach_data", [])
            simplified = _simplify_object_lookup(lookup, approaches_from_browse)
            inserted_this_page += _insert_asteroid(conn, simplified)

    # after_changes not needed; inserted_this_page counts new inserts
        elapsed = time.time() - start_time
        # print progress with page number, total pages (if known), elapsed and inserts
        if total_pages and isinstance(total_pages, int):
            print(f"Completed page {page}/{total_pages} - elapsed {elapsed:.1f}s - inserted {inserted_this_page} new")
        else:
            print(f"Completed page {page} - elapsed {elapsed:.1f}s - inserted {inserted_this_page} new")

        # stop condition: if we reached known total_pages, finish
        if total_pages and isinstance(total_pages, int) and page >= total_pages:
            break

        page += 1

    conn.close()


if __name__ == "__main__":
    # allow overriding start page via env var if desired
    start = int(os.environ.get("ARCHIVE_START_PAGE", START_PAGE))
    run(start)
