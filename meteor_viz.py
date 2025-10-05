"""Lightweight Kepler-orbit visualiser.

This module provides a compact, dependency-free renderer that accepts a NeoWs
object (the JSON shape returned by the NASA NeoWs lookup endpoint) and returns
an inline SVG fragment showing the Sun, Earth's orbit and the asteroid's
osculating orbit derived from the object's `orbital_data` fields.

Goals:
- Use orbital elements from `orbital_data` (a, e, i, ascending_node_longitude,
  perihelion_argument) when available.
- Draw a clean, axis-free 2D top-down view (projection on the ecliptic plane).
- Avoid heavy simulation math — compute the analytic Kepler ellipse and apply
  standard rotations to orient the orbit correctly.
- Return an HTML/SVG fragment that can be embedded directly in templates.
"""

from typing import Any, Dict, Optional, Tuple
import math
import json

__all__ = ["simulate_sun_earth_asteroid"]


def _safe_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if val is None:
            return default
        return float(val)
    except Exception:
        return default


def _parse_orbital_elements(obj: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Extracts and converts orbital elements from a NeoWs object.

    Expected keys inside `orbital_data` (strings or numbers):
      - semi_major_axis (AU)
      - eccentricity
      - inclination (deg)
      - ascending_node_longitude (deg)  -- Ω
      - perihelion_argument (deg)       -- ω

    Returns a dict with floats or None for missing values.
    """
    od = (obj or {}).get("orbital_data") or {}
    return {
        "a": _safe_float(od.get("semi_major_axis")),
        "e": _safe_float(od.get("eccentricity")),
        "i": _safe_float(od.get("inclination")),
        "Omega": _safe_float(od.get("ascending_node_longitude")),
        "omega": _safe_float(od.get("perihelion_argument")),
    }


def _orbit_coords(
    a: float,
    e: float,
    i_deg: float,
    Omega_deg: float,
    omega_deg: float,
    n_points: int = 360,
) -> Tuple[list, list]:
    """Compute top-down (x,y) coordinates for an orbit given classical elements.

    The returned coordinates are in astronomical units (AU). The projection is
    the ecliptic plane (z ignored). Uses standard rotation from orbital plane
    to ecliptic: r * R_z(Omega) * R_x(i) * R_z(omega) * [cos(nu), sin(nu), 0].
    """
    i = math.radians(i_deg or 0.0)
    Omega = math.radians(Omega_deg or 0.0)
    omega = math.radians(omega_deg or 0.0)

    xs = []
    ys = []
    for k in range(n_points + 1):
        nu = 2 * math.pi * k / n_points
        r = a * (1 - e * e) / (1 + e * math.cos(nu))
        # coordinates in orbital plane
        x_orb = r * math.cos(nu)
        y_orb = r * math.sin(nu)

        # rotate by argument of perihelion (omega)
        x1 = x_orb * math.cos(omega) - y_orb * math.sin(omega)
        y1 = x_orb * math.sin(omega) + y_orb * math.cos(omega)

        # rotate by inclination (i) about x-axis
        y2 = y1 * math.cos(i)

        # rotate by longitude of ascending node (Omega) about z-axis
        x = x1 * math.cos(Omega) - y2 * math.sin(Omega)
        y = x1 * math.sin(Omega) + y2 * math.cos(Omega)

        xs.append(x)
        ys.append(y)

    return xs, ys


def _to_svg_path(xs: list, ys: list, scale: float, cx: float, cy: float) -> str:
    pts = []
    for x, y in zip(xs, ys):
        px = cx + x * scale
        py = cy - y * scale
        pts.append(f"{px:.2f},{py:.2f}")
    return "M " + " L ".join(pts)


def simulate_sun_earth_asteroid(
    asteroid_obj: Optional[Dict[str, Any]] = None,
    *,
    width: int = 700,
    height: int = 700,
) -> str:
    """Return an inline SVG fragment showing Sun, Earth's orbit and asteroid orbit.

    Input: `asteroid_obj` should be the full NeoWs lookup object (dict). The
    renderer will read `orbital_data` to obtain orbital elements. If fields are
    missing, sensible defaults are used.
    """
    # Defaults for Earth
    earth_a = 1.0  # AU
    earth_e = 0.0167
    earth_i = 0.0
    earth_Omega = 0.0
    earth_omega = 102.9372  # argument of perihelion (approx), degrees

    # Parse asteroid elements and fallback when absent
    elems = _parse_orbital_elements(asteroid_obj or {})
    a = elems.get("a") if elems.get("a") is not None else 1.3
    e = elems.get("e") if elems.get("e") is not None else 0.25
    i_deg = elems.get("i") if elems.get("i") is not None else 10.0
    Omega_deg = elems.get("Omega") if elems.get("Omega") is not None else 0.0
    omega_deg = elems.get("omega") if elems.get("omega") is not None else 0.0

    # Compute orbit coordinates (AU)
    ast_xs, ast_ys = _orbit_coords(a, e, i_deg, Omega_deg, omega_deg, n_points=360)
    earth_xs, earth_ys = _orbit_coords(earth_a, earth_e, earth_i, earth_Omega, earth_omega, n_points=360)

    # Determine scale to fit both orbits into the canvas with margin
    max_r = 0.0
    for xs, ys in ((ast_xs, ast_ys), (earth_xs, earth_ys)):
        for x, y in zip(xs, ys):
            r = math.hypot(x, y)
            if r > max_r:
                max_r = r
    if max_r <= 0:
        max_r = 1.0

    margin = 0.08
    pad = max(width, height) * margin
    # compute usable canvas size (not used for Plotly rendering below)
    _ = min(width, height) - 2 * pad

    # Build SVG elements ( kept minimal here — SVG paths were computed but
    # the final visualisation uses Plotly 3D rendering below )

    # pick labels
    name = "Unknown"
    try:
        if asteroid_obj and isinstance(asteroid_obj, dict):
            name = (
                asteroid_obj.get("name")
                or asteroid_obj.get("designation")
                or asteroid_obj.get("neo_reference_id")
                or name
            )
    except Exception:
        pass

    # (Perihelion coordinates not required for the Plotly fragment)

    # Build a Plotly-based 3D interactive visualisation (returned as HTML fragment).
    # Create 3D coordinates for both asteroid and Earth (including z from inclination).
    def _orbit_coords_3d(a, e, i_deg, Omega_deg, omega_deg, n_points=360):
        i = math.radians(i_deg or 0.0)
        Omega = math.radians(Omega_deg or 0.0)
        omega = math.radians(omega_deg or 0.0)
        xs = []
        ys = []
        zs = []
        for k in range(n_points + 1):
            nu = 2 * math.pi * k / n_points
            r = a * (1 - e * e) / (1 + e * math.cos(nu))
            x_orb = r * math.cos(nu)
            y_orb = r * math.sin(nu)

            # argument of perihelion rotation
            x1 = x_orb * math.cos(omega) - y_orb * math.sin(omega)
            y1 = x_orb * math.sin(omega) + y_orb * math.cos(omega)

            # rotate by inclination about x-axis
            y2 = y1 * math.cos(i)
            z2 = y1 * math.sin(i)

            # rotate by longitude of ascending node about z-axis
            x = x1 * math.cos(Omega) - y2 * math.sin(Omega)
            y = x1 * math.sin(Omega) + y2 * math.cos(Omega)
            z = z2

            xs.append(x)
            ys.append(y)
            zs.append(z)
        return xs, ys, zs

    n_points = 360
    ast_xs, ast_ys, ast_zs = _orbit_coords_3d(
        a, e, i_deg, Omega_deg, omega_deg, n_points=n_points
    )
    earth_xs, earth_ys, earth_zs = _orbit_coords_3d(
        earth_a,
        earth_e,
        earth_i,
        earth_Omega,
        earth_omega,
        n_points=n_points,
    )

    # Choose initial marker positions (kept for reference)
    # (not used by the Plotly fragment)

    # Build Plotly traces (lines + markers)
    # Build planet orbits up to Mars (approximate elements — adequate for a visual)
    planets = {
        'Mercury': {
            'a': 0.387, 'e': 0.2056, 'i': 7.0,
            'Omega': 48.331, 'omega': 29.124,
            'color': '#b36200', 'size': 3,
        },
        'Venus': {
            'a': 0.723, 'e': 0.0067, 'i': 3.39,
            'Omega': 76.680, 'omega': 54.884,
            'color': '#f59e0b', 'size': 4,
        },
        'Earth': {
            'a': earth_a, 'e': earth_e, 'i': earth_i,
            'Omega': earth_Omega, 'omega': earth_omega,
            'color': '#3b82f6', 'size': 5,
        },
        'Mars': {
            'a': 1.524, 'e': 0.0934, 'i': 1.85,
            'Omega': 49.558, 'omega': 286.537,
            'color': '#ef4444', 'size': 4,
        },
    }

    planet_coords = {}
    for name, p in planets.items():
        xs_p, ys_p, zs_p = _orbit_coords_3d(p['a'], p['e'], p['i'], p['Omega'], p['omega'], n_points=n_points)
        planet_coords[name] = (xs_p, ys_p, zs_p)

    # Orbit lines: asteroid + planets (dotted for asteroid to emphasize motion)
    asteroid_trace = {
        'type': 'scatter3d', 'mode': 'lines', 'x': ast_xs, 'y': ast_ys, 'z': ast_zs,
        'line': {'color': '#ef4444', 'width': 2, 'dash': 'dot'}, 'name': 'Asteroid orbit', 'hoverinfo': 'none'
    }

    planet_orbit_traces = []
    for pname, p in planets.items():
        xs_p, ys_p, zs_p = planet_coords[pname]
        planet_orbit_traces.append({
            'type': 'scatter3d', 'mode': 'lines', 'x': xs_p, 'y': ys_p, 'z': zs_p,
            'line': {'color': p['color'], 'width': 2, 'dash': 'dash'}, 'name': f"{pname} orbit", 'hoverinfo': 'none'
        })

    sun_trace = {
        'type': 'scatter3d',
        'mode': 'markers',
        'x': [0], 'y': [0], 'z': [0],
        'marker': {'color': '#f59e0b', 'size': 10},
        'name': 'Sun',
    }

    # Marker traces (initial positions)
    asteroid_marker = {
        'type': 'scatter3d',
        'mode': 'markers',
        'x': [ast_xs[0]], 'y': [ast_ys[0]], 'z': [ast_zs[0]],
        'marker': {'color': '#ef4444', 'size': 5},
        'name': 'Asteroid',
    }

    planet_marker_traces = []
    for pname, p in planets.items():
        xs_p, ys_p, zs_p = planet_coords[pname]
        planet_marker_traces.append({
            'type': 'scatter3d',
            'mode': 'markers',
            'x': [xs_p[0]], 'y': [ys_p[0]], 'z': [zs_p[0]],
            'marker': {'color': p['color'], 'size': p['size']},
            'name': pname,
        })

    # Trailing asteroid path trace (starts empty)
    asteroid_tail = {
        'type': 'scatter3d',
        'mode': 'lines',
        'x': [], 'y': [], 'z': [],
        'line': {'color': '#ef4444', 'width': 3},
        'name': 'Asteroid trail',
    }

    # Compose final data (orbit lines first, then sun, then markers, then tail)
    data = [asteroid_trace] + planet_orbit_traces + [sun_trace, asteroid_marker] + planet_marker_traces + [asteroid_tail]

    # Prepare animation frames (move asteroid + planet markers along their orbits, update tail)
    frames = []
    step_stride = 1
    # Determine trace indices that will be updated by frames
    # data layout: [0]=asteroid_orbit, [1..N]=planet_orbits, [N+1]=sun,
    # [N+2]=asteroid_marker, [N+3..]=planet_markers..., [last]=asteroid_tail
    n_planets = len(planet_orbit_traces)
    idx_asteroid_marker = 1 + n_planets + 1  # after asteroid + planet_orbits + sun
    idx_first_planet_marker = idx_asteroid_marker + 1
    idx_asteroid_tail = len(data) - 1

    for k in range(0, n_points, step_stride):
        idx = k % n_points
        # build marker positions
        frame_data = []
        traces_idx = []

        # asteroid marker
        frame_data.append({'x': [ast_xs[idx]], 'y': [ast_ys[idx]], 'z': [ast_zs[idx]]})
        traces_idx.append(idx_asteroid_marker)

        # planet markers in same order as planet_marker_traces
        pi = 0
        for pname in planets.keys():
            xs_p, ys_p, zs_p = planet_coords[pname]
            frame_data.append({'x': [xs_p[idx % len(xs_p)]], 'y': [ys_p[idx % len(ys_p)]], 'z': [zs_p[idx % len(zs_p)]]})
            traces_idx.append(idx_first_planet_marker + pi)
            pi += 1

        # trailing asteroid path (up to current index)
        tail_x = ast_xs[: idx + 1]
        tail_y = ast_ys[: idx + 1]
        tail_z = ast_zs[: idx + 1]
        frame_data.append({'x': tail_x, 'y': tail_y, 'z': tail_z})
        traces_idx.append(idx_asteroid_tail)

        frame = {'name': str(idx), 'data': frame_data, 'traces': traces_idx}
        frames.append(frame)

    # Layouts for light and dark themes (transparent background; colors chosen)
    layout_light = {
        "scene": {
            "xaxis": {"showbackground": False, "showgrid": False, "zeroline": False, "visible": False},
            "yaxis": {"showbackground": False, "showgrid": False, "zeroline": False, "visible": False},
            "zaxis": {"showbackground": False, "showgrid": False, "zeroline": False, "visible": False},
            "aspectmode": "data",
        },
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "showlegend": True,
        "margin": {"l": 0, "r": 0, "b": 0, "t": 30},
        "title": {"text": "Sun-Earth-Asteroid", "font": {"color": "#111827"}},
    }

    layout_dark = {
        "scene": {
            "xaxis": {"showbackground": False, "showgrid": False, "zeroline": False, "visible": False},
            "yaxis": {"showbackground": False, "showgrid": False, "zeroline": False, "visible": False},
            "zaxis": {"showbackground": False, "showgrid": False, "zeroline": False, "visible": False},
            "aspectmode": "data",
        },
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "showlegend": True,
        "margin": {"l": 0, "r": 0, "b": 0, "t": 30},
        "title": {"text": "Sun-Earth-Asteroid", "font": {"color": "#ffffff"}},
    }

    # Compose the HTML fragment with a unique container id
    import time
    uid = int(time.time() * 1000) % 1000000
    div_id = f"orbit_plot_{uid}"

    # Compose a single HTML + JS fragment. Build using concatenation to avoid
    # f-string brace-escaping issues when embedding large JS snippets.
    parts = []
    parts.append('<div id="' + div_id + '" style="width:' + str(width) + 'px; height:' + str(height) + 'px;">')
    parts.append('</div>')
    parts.append('<script>')
    parts.append('(function(){')
    parts.append('    const container = document.getElementById(' + json.dumps(div_id) + ');')
    parts.append('    if (!container || typeof Plotly === "undefined") return;')
    parts.append('    const traces = ' + json.dumps(data) + ';')
    parts.append('    const frames = ' + json.dumps(frames) + ';')
    parts.append('    const layoutLight = ' + json.dumps(layout_light) + ';')
    parts.append('    const layoutDark = ' + json.dumps(layout_dark) + ';')
    parts.append('    function detectDark() {')
    parts.append('        try {')
    parts.append('            const bt = document.body && document.body.getAttribute &&')
    parts.append('                document.body.getAttribute("data-theme");')
    parts.append('            if (bt === "dark") return true;')
    parts.append('            if (bt === "light") return false;')
    parts.append('            if (document.documentElement && document.documentElement.classList) {')
    parts.append('                if (document.documentElement.classList.contains("theme-dark")) return true;')
    parts.append('                if (document.documentElement.classList.contains("theme-light")) return false;')
    parts.append('            }')
    parts.append('        } catch (e) {}')
    parts.append('        return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;')
    parts.append('    }')
    parts.append('    const selectedLayout = detectDark() ? layoutDark : layoutLight;')
    parts.append('    // disable scrollZoom to avoid attaching passive-unfriendly wheel/touch listeners')
    parts.append('    const config = {responsive:true, displayModeBar:false, scrollZoom:false};')
    parts.append('    Plotly.newPlot(container, traces, selectedLayout, config).then(function(){')
    parts.append('        // Use a lightweight 60 FPS loop to update markers and trail for a smooth animation')
    parts.append('        let idx = 0;')
    parts.append('        const fps = 60;')
    parts.append('        const interval = Math.round(1000 / fps);')
    parts.append('        const total = frames.length;')
    parts.append('        function step(){')
    parts.append('            const f = frames[idx];')
    parts.append('            try{')
    parts.append('                for(let j=0;j<f.traces.length;j++){')
    parts.append('                    const t = f.traces[j];')
    parts.append('                    const update = f.data[j];')
    parts.append('                    Plotly.restyle(container, update, [t]);')
    parts.append('                }')
    parts.append('            }catch(e){}')
    parts.append('            idx = (idx + 1) % total;')
    parts.append('        }')
    parts.append('        // start loop')
    parts.append('        setInterval(step, interval);')
    parts.append('    });')
    parts.append('})();')
    parts.append('</script>')

    html = "\n".join(parts)

    return html


if __name__ == '__main__':
    # quick smoke test when run directly using the provided meteor.json file
    try:
        with open('meteor.json', 'r') as f:
            data = json.load(f)
            if isinstance(data, list) and data:
                html = simulate_sun_earth_asteroid(data[0])
                print(html)
    except Exception:
        pass

