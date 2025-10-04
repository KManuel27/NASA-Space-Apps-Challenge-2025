from flask import Flask, render_template, request, jsonify
import meteor_viz
import neoWs
from datetime import date, timedelta
from energy_impact import energy_impact_estimation

app = Flask(__name__)


# --------------- Page 1: Static Start Page --------------
@app.route("/")
def start_page():
    return render_template("startPage.html")  # No Python computation yet

@app.route("/available_meteors")
def available_meteors():
    # show page with date pickers and optionally fetch data
    # default range: one week ago -> today
    today = date.today()
    one_week_ago = today - timedelta(days=7)

    # allow overriding via query params
    # We enforce a fixed 7-day window. The user may provide a start date,
    # but it will be clamped so that the 7-day window ends no later than today.
    start_str = request.args.get("start_date", one_week_ago.isoformat())
    try:
        start_dt = date.fromisoformat(start_str)
    except Exception:
        start_dt = one_week_ago

    # Do not allow a start date later than one week ago (so end = start + 7 days <= today)
    if start_dt > one_week_ago:
        start_dt = one_week_ago

    end_dt = start_dt + timedelta(days=7)
    start = start_dt.isoformat()
    end = end_dt.isoformat()

    # Do not fetch NeoWs data when rendering the page — only fetch via AJAX endpoint
    asteroids = None
    error = None

    # render the template and inject initial data for the JS
    # Pass `start_max` so the client can limit the start-date picker to at most one_week_ago
    return render_template(
        "availableMeteors.html",
        start_date=start,
        end_date=end,
        start_max=one_week_ago.isoformat(),
        asteroids=asteroids,
        error=error,
    )

@app.route("/meteors/visualize/<asteroid_id>")
def visualize_asteroid(asteroid_id: str):
    # Default asteroid info (prevents Jinja error)
    asteroid_info = {
        "name": "N/A",
        "diameter": "N/A",
        "closest_approach_date": "N/A",
        "miss_distance": "N/A",
        "velocity": "N/A",
        "risk": "N/A"
    }

    graph_html = "<p>Visualization not available.</p>"

    try:
        # Try to fetch asteroid from NASA NeoWs API
        obj = neoWs.lookup_asteroid(asteroid_id)

        # Safely generate graph
        try:
            graph_html = meteor_viz.simulate_sun_earth_asteroid(obj)
        except TypeError:
            graph_html = meteor_viz.simulate_sun_earth_asteroid()
        except Exception as e:
            graph_html = f"<p>Error generating visualization: {e}</p>"

        # Extract close approach data safely
        close_approach = obj.get("close_approach_data", [])
        close_data = close_approach[0] if close_approach else {}

        # Populate asteroid info
        asteroid_info = {
            "name": obj.get("name", "Unknown"),
            "diameter": obj.get("estimated_diameter", {}).get("meters", {}).get("estimated_diameter_max", "N/A"),
            "closest_approach_date": close_data.get("close_approach_date", "N/A"),
            "miss_distance": close_data.get("miss_distance", {}).get("kilometers", "N/A"),
            "velocity": close_data.get("relative_velocity", {}).get("kilometers_per_second", "N/A"),
            "risk": "High" if obj.get("is_potentially_hazardous_asteroid") else "Minimal"
        }

    except Exception as e:
        # If the API lookup itself fails, render with defaults
        graph_html = f"<p>Error fetching asteroid: {e}</p>"

    # Always render with asteroid_info (even if error)
    return render_template("meteorViz.html", graph_html=graph_html, asteroid_info=asteroid_info)

def _median_diameter_km(neo):
    try:
        d = neo.get("estimated_diameter", {}).get("kilometers", {})
        mn = float(d.get("estimated_diameter_min"))
        mx = float(d.get("estimated_diameter_max"))
        return (mn + mx) / 2.0
    except Exception:
        return None


def _closest_earth_approach(neo):
    cad = neo.get("close_approach_data") or []
    best = None
    for ca in cad:
        ob = str(ca.get("orbiting_body", "")).lower()
        if ob != "earth":
            continue
        try:
            miss = float(ca.get("miss_distance", {}).get("kilometers"))
        except Exception:
            continue
        vel = None
        try:
            vel = float(ca.get("relative_velocity", {}).get("kilometers_per_second"))
        except Exception:
            vel = None
        date = ca.get("close_approach_date_full") or ca.get("close_approach_date") or ""
        if best is None or miss < best["missKm"]:
            best = {"missKm": miss, "velKps": vel, "date": date}
    return best


def _map_neo_to_row(neo):
    dKm = _median_diameter_km(neo)
    ca = _closest_earth_approach(neo)
    missKm = ca["missKm"] if ca else None
    velKps = ca["velKps"] if ca else None
    hazard = (dKm / missKm) if (dKm is not None and missKm) else None
    return {
        "id": neo.get("id"),
        "name": neo.get("name") or neo.get("designation") or neo.get("neo_reference_id"),
        "jpl_url": neo.get("nasa_jpl_url"),
        "approach_date": ca["date"] if ca else None,
        "diameter_km": dKm,
        "miss_distance_km": missKm,
        "velocity_kps": velKps,
        "hazard_score": hazard,
        "_raw": neo,
    }


# Internal AJAX endpoint to compute impact energy and ring radii
@app.route("/api/energy")
def api_energy():
    """
    Returns energy (Mt TNT) and approx ring radii in meters for given inputs.
    Query params:
      diameter_m (required) - diameter in meters
      velocity_kms (required) - km/s
      density_kg_m3 (optional) - default 3000
    """
    try:
        diameter_m = float(request.args.get('diameter_m', '0'))
        velocity_kms = float(request.args.get('velocity_kms', '0'))
        density_kg_m3 = float(request.args.get('density_kg_m3', '3000'))
        # use single-value estimation: pass same value as min/max in km
        d_km = diameter_m / 1000.0
        mt = energy_impact_estimation(d_km, d_km, velocity_kms, density_kg_m3)
        # cube-root scaling for radii (same formula as client)
        r20km = 1.2 * (mt ** (1/3))
        r5km = 3.2 * (mt ** (1/3))
        r1km = 7.0 * (mt ** (1/3))
        rings_m = [r20km * 1000, r5km * 1000, r1km * 1000]
        return jsonify({"mt": mt, "rings_m": rings_m})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# Internal AJAX endpoint to fetch hazardous asteroids for a date range


@app.route("/available_meteors.json")
def available_meteors_json():
    # Return JSON for the requested start date window. This is called by the client via AJAX.
    today = date.today()
    one_week_ago = today - timedelta(days=7)
    start_str = request.args.get("start_date", one_week_ago.isoformat())
    try:
        start_dt = date.fromisoformat(start_str)
    except Exception:
        start_dt = one_week_ago
    if start_dt > one_week_ago:
        start_dt = one_week_ago
    end_dt = start_dt + timedelta(days=7)
    start = start_dt.isoformat()
    end = end_dt.isoformat()

    print(f"[SERVER] JSON endpoint called; start={start} end={end}")
    try:
        rows = neoWs.get_hazardous_asteroids(start, end)
        # If the API returned full NeoWs objects, map them to flat rows
        if isinstance(rows, list) and rows and isinstance(rows[0], dict) and "estimated_diameter" in rows[0]:
            mapped = [_map_neo_to_row(r) for r in rows if r.get("is_potentially_hazardous_asteroid")]
            print(f"[SERVER] JSON endpoint returning {len(mapped)} mapped rows")
            return jsonify(mapped)
        # otherwise return as-is
        print(f"[SERVER] JSON endpoint returning {len(rows) if isinstance(rows, list) else 'unknown'} items")
        return jsonify(rows)
    except Exception as e:
        print(f"[SERVER] JSON endpoint error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/map")
def map_page():
    return render_template("map.html")


if __name__ == "__main__":
    app.run(debug=True)
