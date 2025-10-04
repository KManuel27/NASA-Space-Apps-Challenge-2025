from flask import Flask, render_template, request, jsonify
import meteor_viz
import neoWs
from datetime import date, timedelta

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
    start_str = request.args.get('start_date', one_week_ago.isoformat())
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


@app.route('/meteors/visualize/<asteroid_id>')
def visualize_asteroid(asteroid_id: str):
    # Lookup asteroid from NeoWs and render the meteor visualization page
    try:
        obj = neoWs.lookup_asteroid(asteroid_id)
    except Exception as e:
        return render_template('meteorViz.html', graph_html=f'<p>Error fetching asteroid: {e}</p>')

    # produce graph HTML by passing the asteroid object to meteor_viz
    try:
        graph_html = meteor_viz.simulate_sun_earth_asteroid(obj)
    except TypeError:
        # fallback to no-arg function if meteor_viz expects no param
        graph_html = meteor_viz.simulate_sun_earth_asteroid()

    return render_template('meteorViz.html', graph_html=graph_html)


def _median_diameter_km(neo):
    try:
        d = neo.get('estimated_diameter', {}).get('kilometers', {})
        mn = float(d.get('estimated_diameter_min'))
        mx = float(d.get('estimated_diameter_max'))
        return (mn + mx) / 2.0
    except Exception:
        return None


def _closest_earth_approach(neo):
    cad = neo.get('close_approach_data') or []
    best = None
    for ca in cad:
        ob = str(ca.get('orbiting_body', '')).lower()
        if ob != 'earth':
            continue
        try:
            miss = float(ca.get('miss_distance', {}).get('kilometers'))
        except Exception:
            continue
        vel = None
        try:
            vel = float(ca.get('relative_velocity', {}).get('kilometers_per_second'))
        except Exception:
            vel = None
        date = ca.get('close_approach_date_full') or ca.get('close_approach_date') or ''
        if best is None or miss < best['missKm']:
            best = {'missKm': miss, 'velKps': vel, 'date': date}
    return best


def _map_neo_to_row(neo):
    dKm = _median_diameter_km(neo)
    ca = _closest_earth_approach(neo)
    missKm = ca['missKm'] if ca else None
    velKps = ca['velKps'] if ca else None
    hazard = (dKm / missKm) if (dKm is not None and missKm) else None
    return {
        'id': neo.get('id'),
        'name': neo.get('name') or neo.get('designation') or neo.get('neo_reference_id'),
        'jpl_url': neo.get('nasa_jpl_url'),
        'approach_date': ca['date'] if ca else None,
        'diameter_km': dKm,
        'miss_distance_km': missKm,
        'velocity_kps': velKps,
        'hazard_score': hazard,
        '_raw': neo,
    }


@app.route('/available_meteors.json')
def available_meteors_json():
    # Return JSON for the requested start date window. This is called by the client via AJAX.
    today = date.today()
    one_week_ago = today - timedelta(days=7)
    start_str = request.args.get('start_date', one_week_ago.isoformat())
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
        if isinstance(rows, list) and rows and isinstance(rows[0], dict) and 'estimated_diameter' in rows[0]:
            mapped = [_map_neo_to_row(r) for r in rows if r.get('is_potentially_hazardous_asteroid')]
            print(f"[SERVER] JSON endpoint returning {len(mapped)} mapped rows")
            return jsonify(mapped)
        # otherwise return as-is
        print(f"[SERVER] JSON endpoint returning {len(rows) if isinstance(rows, list) else 'unknown'} items")
        return jsonify(rows)
    except Exception as e:
        print(f"[SERVER] JSON endpoint error: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
