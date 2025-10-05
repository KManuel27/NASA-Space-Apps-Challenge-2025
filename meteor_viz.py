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
tca_date = datetime(2025, 10, 6)

# Earth orbital elements
a_earth = AU
e_earth = 0.0167
i_earth = 0.0
T_earth = 365.25 * 24 * 3600

# Simulation setup
animation_days = 365
dt = 60 * 60 * 24  # 1 day
time_days = np.arange(animation_days)
time_seconds = time_days * dt
num_frames = animation_days


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
    return 2 * np.arctan2(np.sqrt(1 + e) * np.sin(E / 2),
                          np.sqrt(1 - e) * np.cos(E / 2))

def position_from_elements(a, e, i, T, t_seconds, M0=0.0, omega=0.0, Omega=0.0):
    """Compute heliocentric 3D position including inclination, argument of perihelion, and longitude of node."""
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


# Earth position

M0_earth = 0.0
earth_positions = np.array([
    position_from_elements(a_earth, e_earth, i_earth, T_earth, t, M0_earth)
    for t in time_seconds
])


# USER INPUTS — Asteroid orbital parameters

asteroids_input = [
    {
        "name": "2021 ED5",
        "color": "red",
        "tca_date": "2025-10-06",
        "diameter_min_km": 0.2469192656,
        "diameter_max_km": 0.5521282628,
        "M_deg": 20.69381708571853,
        "q_au": 0.693,
        "i_deg": 5.906333965846378,
        "tp_bary": "2460911.548469043960",
        "T_days": 1547.445355853369,
        "Q_au": 2.618,
        "n_deg_per_day": 0.2326414943430884,
        "miss_distance_au": 0.0728452984,
        "a_au": 2.618250911402056,
        "e": 0.7341366398164377,
        "omega_deg": 112.66148628257,
        "Omega_deg": 182.1326382918859
    },
    {
        "name": "2006 SS134",
        "color": "orange",
        "tca_date": "2025-10-01",
        "diameter_min_km": 0.2,
        "diameter_max_km": 0.3,
        "M_deg": 86.83611608273382,
        "q_au": 0.6536299112981256,
        "i_deg": 19.53384221663039,
        "tp_bary": "2460888.765349326200",
        "T_days": 463.2228622966487,
        "Q_au": 1.689651073171432,
        "n_deg_per_day": 0.7771637138441916,
        "miss_distance_au": 0.0812495489,
        "a_au": 1.171640492234779,
        "e": 0.4421241706563107,
        "omega_deg": 256.174689651037,
        "Omega_deg": 8.987533082435228
    },
    {
        "name": "2020 GA2",
        "color": "magenta",
        "tca_date": "2025-10-07",
        "diameter_min_km": 0.1572370824,
        "diameter_max_km": 0.3515928047,
        "M_deg": 352.3180733052727,
        "q_au": 0.7343999690062724,
        "i_deg": 42.98274472586962,
        "tp_bary": "2461011.806245622687",
        "T_days": 529.8473398556577,
        "Q_au": 1.828499375025615,
        "n_deg_per_day": 0.6794409878476924,
        "miss_distance_au": 0.2978718991,
        "a_au": 1.281449672015944,
        "e": 0.4268990932348258,
        "omega_deg": 93.01563318280928,
        "Omega_deg": 22.88914007416489
    },
    {
        "name": "1991 GO",
        "color": "green",
        "tca_date": "2025-10-01",
        "diameter_min_km": 0.2538370294,
        "diameter_max_km": 0.5675968529,
        "M_deg": 2.405072222117659,
        "q_au": 0.6659157393293433,
        "i_deg": 9.554568968911488,
        "tp_bary": "2460993.978190500453",
        "T_days": 976.2082810842199,
        "Q_au": 3.185845596319214,
        "n_deg_per_day": 0.3687737616814397,
        "miss_distance_au": 0.4680004601,
        "a_au": 1.925880667824279,
        "e": 0.6542279329894064,
        "omega_deg": 89.77142930391584,
        "Omega_deg": 23.94264848560579
    },
    {
        "name": "2021 SZ4",
        "color": "pink",
        "tca_date": "2025-10-04",
        "diameter_min_km": 0.2140695897,
        "diameter_max_km": 0.4786741544,
        "M_deg": 6.552951025467921,
        "q_au": 0.2971912349744232,
        "i_deg": 26.40210694019939,
        "tp_bary": "2460987.759115001827",
        "T_days": 699.9470286770122,
        "Q_au": 2.788419669124214,
        "n_deg_per_day": 0.514324634937654,
        "miss_distance_au": 0.4805731264,
        "a_au": 1.542805452049318,
        "e": 0.807369597651044,
        "omega_deg": 129.5871099387515,
        "Omega_deg": 28.37777260831761
    }
]


# Convert Input Parameters to Orbital Data

asteroid_sets = []
for asteroid in asteroids_input:
    name = asteroid["name"]
    color = asteroid["color"]
    a = asteroid["a_au"] * AU
    e = asteroid["e"]
    i = np.radians(asteroid["i_deg"])
    omega = np.radians(asteroid["omega_deg"])
    Omega = np.radians(asteroid["Omega_deg"])
    T_ast = asteroid["T_days"] * 86400.0
    M0 = np.radians(asteroid["M_deg"])
    avg_diam = 0.5 * (asteroid["diameter_min_km"] + asteroid["diameter_max_km"])

    tca_date_ast = datetime.strptime(asteroid["tca_date"], "%Y-%m-%d")
    tca_days_ast = (tca_date_ast - orbit_determination_date).days
    tca_seconds_ast = tca_days_ast * 86400.0

    pos = np.array([
        position_from_elements(a, e, i, T_ast, t, M0, omega, Omega)
        for t in time_seconds
    ])

    asteroid_sets.append((pos, color, name, avg_diam, tca_seconds_ast))


# Sun sphere

def create_sphere(center, radius, color, resolution=25):
    u = np.linspace(0, 2 * np.pi, resolution)
    v = np.linspace(0, np.pi, resolution)
    x = center[0] + radius * np.outer(np.cos(u), np.sin(v))
    y = center[1] + radius * np.outer(np.sin(u), np.sin(v))
    z = center[2] + radius * np.outer(np.ones_like(u), np.cos(v))
    return go.Surface(x=x, y=y, z=z,
                      colorscale=[[0, color], [1, color]],
                      opacity=0.9, showscale=False, hoverinfo='skip')

sun_sphere = create_sphere([0, 0, 0], R_sun, "yellow")


# Frames for animation

frames = []
for k in range(num_frames):
    frame_data = []

    frame_data.append(dict(
        type='surface', x=sun_sphere.x, y=sun_sphere.y, z=sun_sphere.z,
        showscale=False, opacity=0.9
    ))

    frame_data.append(dict(
        type='scatter3d', x=[earth_positions[k, 0]], y=[earth_positions[k, 1]], z=[earth_positions[k, 2]],
        mode='markers', marker=dict(size=1.5, color='blue'), name='Earth', showlegend=False
    ))
    frame_data.append(dict(
        type='scatter3d', x=earth_positions[:k+1, 0], y=earth_positions[:k+1, 1], z=earth_positions[:k+1, 2],
        mode='lines', line=dict(color='blue'), showlegend=False
    ))

    frame_data.append(dict(type='scatter3d', x=[0], y=[0], z=[R_sun*1.03],
                           mode='text', text=['Sun'], textfont=dict(size=14, color='yellow'), showlegend=False))
    frame_data.append(dict(type='scatter3d',
                           x=[earth_positions[k, 0]], y=[earth_positions[k, 1]], z=[earth_positions[k, 2] + R_earth * 2000],
                           mode='text', text=['Earth'], textfont=dict(size=12, color='blue'), showlegend=False))

    for (pos, color, label, diam, tca_s) in asteroid_sets:
        frame_data.append(dict(
            type='scatter3d', x=[pos[k, 0]], y=[pos[k, 1]], z=[pos[k, 2]],
            mode='markers', marker=dict(size=1.2, color=color),
            name=label, showlegend=False
        ))
        frame_data.append(dict(
            type='scatter3d', x=pos[:k+1, 0], y=pos[:k+1, 1], z=pos[:k+1, 2],
            mode='lines', line=dict(color=color), showlegend=False
        ))
        frame_data.append(dict(
            type='scatter3d',
            x=[pos[k, 0]], y=[pos[k, 1]], z=[pos[k, 2] + R_asteroid * 2000],
            mode='text', text=[label], textfont=dict(size=12, color=color),
            showlegend=False
        ))

    frames.append(go.Frame(data=frame_data, name=str(k)))


# Slider setup

date_labels = [orbit_determination_date + timedelta(days=int(d)) for d in time_days]
slider_steps = []
for k in range(num_frames):
    label_text = date_labels[k].strftime("%b %d")
    color = "lightgray"
    slider_steps.append(dict(
        method='animate',
        args=[[str(k)], dict(mode='immediate',
                             frame=dict(duration=0, redraw=True),
                             transition=dict(duration=0))],
        label=f"<span style='color:{color}'>{label_text}</span>"
    ))


# Layout

axis_range = 4 * AU
hidden_axis = dict(range=[-axis_range, axis_range],
                   showbackground=False, showgrid=False,
                   showticklabels=False, zeroline=False, color="black")

layout = go.Layout(
    title="Sun–Earth–Asteroids System",
    width=1000, height=850,
    scene=dict(
        xaxis=hidden_axis, yaxis=hidden_axis, zaxis=hidden_axis,
        aspectmode='manual', aspectratio=dict(x=1, y=1, z=1),
        camera=dict(eye=dict(x=1.8, y=1.8, z=1.2)), dragmode='orbit'
    ),
    paper_bgcolor='black', plot_bgcolor='black',
    font=dict(color='white'), showlegend=False,
    updatemenus=[dict(
        type='buttons', showactive=False, y=1.05, x=1.18,
        buttons=[
            dict(label='Play', method='animate',
                 args=[None, {"frame": {"duration": 60, "redraw": True},
                              "fromcurrent": True, "transition": {"duration": 0}}]),
            dict(label='Pause', method='animate',
                 args=[[None], {"frame": {"duration": 0, "redraw": False},
                                "mode": "immediate", "transition": {"duration": 0}}])
        ]
    )],
    sliders=[dict(
        steps=slider_steps, active=0, x=0.1, y=-0.05, len=0.8,
        currentvalue=dict(prefix="Current Date: ", visible=True,
                          font=dict(color="white", size=14)),
        pad=dict(b=20, t=40), ticklen=6, tickwidth=2,
        tickcolor="red", bgcolor="#2b2b2b",
        bordercolor="gray", borderwidth=1
    )]
)

# ====================================
# Initial Scene
# ====================================
initial_data = [
    dict(type='surface', x=sun_sphere.x, y=sun_sphere.y, z=sun_sphere.z,
         showscale=False, opacity=0.9)
]

initial_data.extend([
    dict(type='scatter3d', x=[earth_positions[0, 0]], y=[earth_positions[0, 1]], z=[earth_positions[0, 2]],
         mode='markers', marker=dict(size=1.5, color='blue'), showlegend=False),
    dict(type='scatter3d', x=[], y=[], z=[], mode='lines', line=dict(color='blue'), showlegend=False),
    dict(type='scatter3d', x=[0], y=[0], z=[R_sun*1.03],
         mode='text', text=['Sun'], textfont=dict(size=14, color='yellow'), showlegend=False),
    dict(type='scatter3d',
         x=[earth_positions[0, 0]], y=[earth_positions[0, 1]], z=[earth_positions[0, 2] + R_earth*2000],
         mode='text', text=['Earth'], textfont=dict(size=12, color='blue'), showlegend=False)
])

for (pos, color, label, diam, tca_s) in asteroid_sets:
    initial_data.extend([
        dict(type='scatter3d', x=[pos[0, 0]], y=[pos[0, 1]], z=[pos[0, 2]],
             mode='markers', marker=dict(size=1.2, color=color), showlegend=False),
        dict(type='scatter3d', x=[], y=[], z=[], mode='lines', line=dict(color=color), showlegend=False),
        dict(type='scatter3d',
             x=[pos[0, 0]], y=[pos[0, 1]], z=[pos[0, 2] + R_asteroid*2000],
             mode='text', text=[label], textfont=dict(size=12, color=color), showlegend=False)
    ])



fig = go.Figure(data=initial_data, layout=layout, frames=frames)
fig.show()


