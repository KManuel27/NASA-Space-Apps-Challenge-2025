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

import numpy as np
import plotly.graph_objs as go
import plotly.io as pio
from datetime import datetime, timedelta

# ====================================
# Constants
# ====================================
G = 6.67430e-11
M_sun = 1.989e30
R_sun = 6.9634e8
R_earth = 6.371e6
R_asteroid = 5e5
AU = 1.496e11
mu_sun = G * M_sun


# Start configuration — Earth at perihelion (Jan 4, 2025)
orbit_determination_date = datetime(2025, 1, 4)

# Earth orbital elements
a_earth = AU
e_earth = 0.0167
i_earth = 0.0
T_earth = 365.25 * 24 * 3600

# Default simulation setup
DEFAULT_DAYS = 365
DT = 60 * 60 * 24  # 1 day


# Orbital mechanics functions

def kepler_E(M, e, tol=1e-12):
    E = M if e < 0.8 else np.pi
    while True:
        dE = (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
        E -= dE
        if abs(dE) < tol:
            break
    return E


def true_anomaly(E, e):
    return 2 * np.arctan2(
        np.sqrt(1 + e) * np.sin(E / 2),
        np.sqrt(1 - e) * np.cos(E / 2)
    )


def position_from_elements(a, e, i, T, t_seconds, M0=0.0, omega=0.0, Omega=0.0):
    """Compute heliocentric 3D position including inclination, argument of
    perihelion, and longitude of node.
    """
    M = (2 * np.pi * (t_seconds / T) + M0) % (2 * np.pi)
    E = kepler_E(M, e)
    nu = true_anomaly(E, e)
    r = a * (1 - e**2) / (1 + e * np.cos(nu))
    x_orb = r * np.cos(nu)
    y_orb = r * np.sin(nu)

    # Rotate from orbital plane to heliocentric ecliptic coordinates
    x = (np.cos(Omega) * np.cos(omega) - np.sin(Omega) * np.sin(omega) * np.cos(i)) * x_orb + \
        (-np.cos(Omega) * np.sin(omega) - np.sin(Omega) * np.cos(omega) * np.cos(i)) * y_orb
    y = (np.sin(Omega) * np.cos(omega) + np.cos(Omega) * np.sin(omega) * np.cos(i)) * x_orb + \
        (-np.sin(Omega) * np.sin(omega) + np.cos(Omega) * np.cos(omega) * np.cos(i)) * y_orb
    z = (np.sin(omega) * np.sin(i)) * x_orb + (np.cos(omega) * np.sin(i)) * y_orb

    return np.array([x, y, z])


# The visualiser is provided as a function so it can be called from Flask routes.
def simulate_sun_earth_asteroid(neo=None, days=DEFAULT_DAYS, samples=180):
    """
    Generate an embeddable Plotly HTML fragment showing the Sun, Earth's orbit and
    a single asteroid orbit (from `neo` orbital_data) or a simple demo if `neo` is None.

    Returns a string containing an HTML fragment (not a full page). The application
    template already includes the Plotly script, so this fragment omits the library.
    """

    # time grid
    time_days = np.linspace(0, days, samples)
    time_seconds = time_days * DT

    # Earth positions
    M0_earth = 0.0
    earth_positions = np.array([
        position_from_elements(a_earth, e_earth, i_earth, T_earth, t, M0_earth)
        for t in time_seconds
    ])

    # Simple planetary semi-major axes (AU) and colours - relative distances
    # We'll compute circular-ish orbits (e=0) in the ecliptic for visual context
    planets_info = [
        ("Mercury", 0.387 * AU, "lightgray"),
        ("Venus", 0.723 * AU, "goldenrod"),
        ("Mars", 1.524 * AU, "orangered"),
        ("Jupiter", 5.203 * AU, "sandybrown"),
    ]

    planet_sets = []
    for idx, (pname, a_p, pcolor) in enumerate(planets_info):
        # circular orbit approximation for visualisation
        T_p = 2 * np.pi * np.sqrt((a_p ** 3) / mu_sun)
        # offset the mean anomaly slightly per planet so markers start at different positions
        M0_p = np.radians(360.0 * (idx / max(1, len(planets_info))))
        # animation positions sampled on the main time grid
        pos_p_anim = np.array([position_from_elements(a_p, 0.0, 0.0, T_p, t, M0_p) for t in time_seconds])
        # full-orbit line sampled densely over one orbital period so the orbit shows completely
        orbit_samples = max(360, samples)
        t_full = np.linspace(0, T_p, orbit_samples)
        pos_p_full = np.array([position_from_elements(a_p, 0.0, 0.0, T_p, t, M0_p) for t in t_full])
        planet_sets.append((pos_p_anim, pos_p_full, pcolor, pname))

    # Parse a single asteroid from neo if provided, otherwise a small demo
    asteroid_sets = []
    if neo and isinstance(neo, dict):
        od = neo.get('orbital_data', {})
        try:
            a = float(od.get('semi_major_axis') or od.get('a') or od.get('a_au')) * AU
            e = float(od.get('eccentricity') or od.get('e'))
            i = np.radians(float(od.get('inclination') or od.get('i') or 0.0))
            omega = np.radians(float(
                od.get('perihelion_argument')
                or od.get('perihelion_argument_deg')
                or od.get('perihelion_arg')
                or od.get('pericenter_argument')
                or 0.0
            ))
            Omega = np.radians(float(od.get('ascending_node_longitude') or od.get('node_longitude') or 0.0))
            T_ast_days = float(od.get('orbital_period') or od.get('period') or od.get('period_yr', 0.0))
            if T_ast_days and T_ast_days < 1e5:
                T_ast = T_ast_days * 86400.0
            else:
                # fallback: compute period from semi-major axis using Kepler's third law
                T_ast = 2 * np.pi * np.sqrt((a**3) / mu_sun)
            M0 = np.radians(float(od.get('mean_anomaly') or od.get('M') or 0.0))
            label = neo.get('name') or neo.get('designation') or 'Asteroid'
            color = 'crimson'
        except Exception:
            # fallback to demo below
            neo = None

    if not neo:
        # small demo asteroid (a few elements) — visible and visually pleasing
        label = 'Demo Asteroid'
        color = 'magenta'
        a = 1.3 * AU
        e = 0.35
        i = np.radians(12.0)
        T_ast = 2 * np.pi * np.sqrt((a**3) / mu_sun)
    pos_anim = np.array([
        position_from_elements(a, e, i, T_ast, t, M0, omega, Omega)
        for t in time_seconds
    ])
    # sample full asteroid orbit densely so the complete orbit line is visible
    orbit_samples_ast = max(360, samples)
    t_full_ast = np.linspace(0, T_ast, orbit_samples_ast)
    pos_full = np.array([
        position_from_elements(a, e, i, T_ast, t, M0, omega, Omega) for t in t_full_ast
    ])
    asteroid_sets.append((pos_anim, pos_full, color, label))

    # Create plotly figure (single scene, interactive) with animation frames and a slider
    # Compute an axis range that fits the outermost orbit (planets or asteroid)
    # so the largest orbit (e.g., Jupiter) appears near the edge while keeping
    # Earth, other planets and the asteroid comfortably visible.
    # derive radii from full-orbit samples
    try:
        max_planet_radius = max(np.max(np.linalg.norm(ps_full, axis=1)) for (_pa, ps_full, _pc, _pn) in planet_sets)
    except Exception:
        max_planet_radius = 3.0 * AU

    try:
        # compute max radius per asteroid full-orbit sample and take the maximum
        asteroid_radii = [np.max(np.linalg.norm(ast_full, axis=1))
                          for (ast_anim, ast_full, _ac, _al) in asteroid_sets]
        max_asteroid_radius = max(asteroid_radii) if asteroid_radii else 0.0
    except Exception:
        max_asteroid_radius = 0.0

    earth_radius = float(np.max(np.linalg.norm(earth_positions, axis=1))) if earth_positions.size else 1.0 * AU

    # take the largest radius and add a small padding
    max_radius = max(max_planet_radius, max_asteroid_radius, earth_radius, 3.0 * AU)
    axis_range = float(max_radius * 1.08)

    hidden_axis = dict(
        range=[-axis_range, axis_range], showbackground=False, showgrid=False,
        showticklabels=False, zeroline=False, color='white', title={'text': ''}
    )

    fig = go.Figure()

    # Static traces: Sun marker, Earth full orbit, Asteroid full orbit
    # Sun (legend enabled)
    fig.add_trace(go.Scatter3d(x=[0], y=[0], z=[0], mode='markers',
                               marker=dict(size=18, color='yellow'), name='Sun', showlegend=True))

    # Earth full orbit (legend enabled)
    fig.add_trace(go.Scatter3d(x=earth_positions[:, 0], y=earth_positions[:, 1], z=earth_positions[:, 2],
                               mode='lines', line=dict(color='royalblue', width=2),
                               name='Earth Orbit', showlegend=True))

    # Earth marker (moving) - do not duplicate legend entry
    fig.add_trace(go.Scatter3d(x=[earth_positions[0, 0]], y=[earth_positions[0, 1]], z=[earth_positions[0, 2]],
                               mode='markers', marker=dict(size=6, color='blue'), name='Earth', showlegend=False))

    # Earth trail (will be updated in frames)
    fig.add_trace(go.Scatter3d(x=[], y=[], z=[], mode='lines', line=dict(color='royalblue', width=2),
                               name='Earth Trail', showlegend=False))

    # Planet orbits and markers (Mercury..Jupiter)
    for (pos_p_anim, pos_p_full, pcolor, pname) in planet_sets:
        # full orbit line (legend entry)
        fig.add_trace(go.Scatter3d(x=pos_p_full[:, 0], y=pos_p_full[:, 1], z=pos_p_full[:, 2], mode='lines',
                                   line=dict(color=pcolor, width=1), name=f'{pname} Orbit', showlegend=True))
        # planet marker (moving)
        fig.add_trace(go.Scatter3d(x=[pos_p_anim[0, 0]], y=[pos_p_anim[0, 1]], z=[pos_p_anim[0, 2]], mode='markers',
                                   marker=dict(size=4, color=pcolor), name=pname, showlegend=False))
        # trail for planet
        fig.add_trace(go.Scatter3d(x=[], y=[], z=[], mode='lines', line=dict(color=pcolor, width=1),
                                   name=f'{pname} Trail', showlegend=False))

    # Asteroid full orbit
    for (pos_anim, pos_full, color, label) in asteroid_sets:
        # full asteroid orbit (legend entry)
        fig.add_trace(go.Scatter3d(x=pos_full[:, 0], y=pos_full[:, 1], z=pos_full[:, 2], mode='lines',
                                   line=dict(color=color, width=2), name=f'{label} Orbit', showlegend=True))

        # Asteroid marker (moving)
        fig.add_trace(go.Scatter3d(x=[pos_anim[0, 0]], y=[pos_anim[0, 1]], z=[pos_anim[0, 2]], mode='markers',
                                   marker=dict(size=5, color=color), name=label, showlegend=False))

        # Asteroid trail (updated per frame)
        fig.add_trace(go.Scatter3d(x=[], y=[], z=[], mode='lines', line=dict(color=color, width=2),
                                   name=f'{label} Trail', showlegend=False))

    # Build frames
    frames = []
    for k in range(len(time_seconds)):
        frame_traces = []
        # Sun (static)
        frame_traces.append(dict(type='scatter3d', x=[0], y=[0], z=[0]))

        # Earth full orbit (static)
        frame_traces.append(dict(type='scatter3d', x=earth_positions[:, 0].tolist(),
                                 y=earth_positions[:, 1].tolist(), z=earth_positions[:, 2].tolist()))

        # Earth marker (moving)
        ex, ey, ez = earth_positions[k]
        frame_traces.append(dict(type='scatter3d', x=[ex], y=[ey], z=[ez]))

        # Earth trail (up to k)
        frame_traces.append(dict(type='scatter3d', x=earth_positions[:k+1, 0].tolist(),
                                 y=earth_positions[:k+1, 1].tolist(), z=earth_positions[:k+1, 2].tolist()))

        # Planet orbits and markers (static orbit, moving marker, trail)
        for (pos_p_anim, pos_p_full, pcolor, pname) in planet_sets:
            # full orbit (static)
            frame_traces.append(dict(type='scatter3d', x=pos_p_full[:, 0].tolist(),
                                     y=pos_p_full[:, 1].tolist(), z=pos_p_full[:, 2].tolist()))
            # planet marker (moving)
            px, py, pz = pos_p_anim[k]
            frame_traces.append(dict(type='scatter3d', x=[px], y=[py], z=[pz]))
            # planet trail
            frame_traces.append(dict(type='scatter3d', x=pos_p_anim[:k+1, 0].tolist(),
                                     y=pos_p_anim[:k+1, 1].tolist(), z=pos_p_anim[:k+1, 2].tolist()))

        # Asteroid full orbit (static)
        for (pos_anim, pos_full, color, label) in asteroid_sets:
            frame_traces.append(dict(type='scatter3d', x=pos_full[:, 0].tolist(),
                                     y=pos_full[:, 1].tolist(), z=pos_full[:, 2].tolist()))

            # Asteroid marker
            ax, ay, az = pos_anim[k]
            frame_traces.append(dict(type='scatter3d', x=[ax], y=[ay], z=[az]))

            # Asteroid trail
            frame_traces.append(dict(type='scatter3d', x=pos_anim[:k+1, 0].tolist(),
                                     y=pos_anim[:k+1, 1].tolist(), z=pos_anim[:k+1, 2].tolist()))

        frames.append(go.Frame(data=frame_traces, name=str(k)))

    # Slider steps
    slider_steps = []
    date_labels = [orbit_determination_date + timedelta(days=int(d)) for d in time_days]
    for k in range(len(time_seconds)):
        label_text = date_labels[k].strftime('%b %d')
        slider_steps.append(dict(
            method='animate',
            args=[[str(k)], dict(mode='immediate', frame=dict(duration=0, redraw=True), transition=dict(duration=0))],
            label=label_text
        ))

    # Layout with play/pause and slider
    fig.update_layout(
        scene=dict(
            xaxis=hidden_axis, yaxis=hidden_axis, zaxis=hidden_axis,
            aspectmode='manual', aspectratio=dict(x=1, y=1, z=0.4),
            # set a stable, normalized camera view so "zoom" and angle are
            # controlled consistently regardless of absolute data units.
            # These normalized eye values place Jupiter's orbit near the frame
            # edge while keeping inner planets and the asteroid visible.
            camera=dict(
                eye=dict(x=0.6, y=0.6, z=0.6),
                center=dict(x=0, y=0, z=0),
                up=dict(x=0, y=0, z=1),
                projection=dict(type='perspective')
            )
        ),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        # add right margin to leave room for the info sidebar
        margin=dict(l=0, r=380, t=30, b=0),
        height=720,
        title=f"Sun – Earth – {label}",
        showlegend=True,
        # legend acts as the key for traces (orbits and Sun)
        legend=dict(
            orientation='v',
            x=0.02, y=0.98,
            xanchor='left', yanchor='top',
            bgcolor='rgba(0,0,0,0)',
            bordercolor='rgba(0,0,0,0.2)'
        ),
        updatemenus=[
            dict(
                type='buttons',
                showactive=False,
                x=0.02, y=0.02,
                xanchor='left', yanchor='bottom',
                pad=dict(t=8, r=8, b=8, l=8),
                buttons=[
                    dict(
                        label='Play', method='animate',
                        args=[None, {"frame": {"duration": 80, "redraw": True},
                                     "fromcurrent": True, "transition": {"duration": 0}}]
                    ),
                    dict(
                        label='Pause', method='animate',
                        args=[[None], {"frame": {"duration": 0, "redraw": False},
                                       "mode": "immediate", "transition": {"duration": 0}}]
                    )
                ]
            )
        ],
        sliders=[
            dict(
                steps=slider_steps,
                active=0,
                x=0.1, y=-0.05,
                len=0.8,
                currentvalue=dict(prefix='Current Date: ', visible=True),
                pad=dict(b=20, t=40)
            )
        ]
    )

    fig.frames = frames

    # Return an HTML fragment without including the Plotly.js script (template already has it)
    html_fragment = pio.to_html(fig, include_plotlyjs=False, full_html=False)

    # Ensure the animation is paused on load: append a small script that cancels any autoplay
    stop_script = '''
<script>
  (function(){
    function stopAnimation(){
      var gd = document.querySelector('.js-plotly-plot');
      if(!gd || typeof Plotly === 'undefined') return;
      try{ Plotly.animate(gd, [], {mode:'immediate'}); }catch(e){}
    }
    window.addEventListener('load', function(){ setTimeout(stopAnimation, 120); });
    setTimeout(stopAnimation, 500);
  })();
</script>
'''
    html_fragment += stop_script
    return html_fragment


# End of file: this module exposes simulate_sun_earth_asteroid


