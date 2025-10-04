import plotly.graph_objs as go
import plotly.io as pio
import numpy as np
from typing import Any, Dict, List, Optional
from datetime import datetime

# Module-level public API
__all__ = ["Simulator", "simulate_sun_earth_asteroid"]


# Physical constants and defaults grouped in a namespace-like dict


# UNLESS SPECIFIED ALL UNITS ARE IN STANDARD SI UNITS
# The system is centred about the sun and Keplerian mechanics assumed for the visualisation.

# Constants
G = 6.67430e-11
M_sun = 1.989e30
M_earth = 5.972e24
R_sun = 6.9634e8
R_earth = 6.371e6
R_asteroid = 5e5 # Assumed here
AU = 1.496e11
mu_sun = G * M_sun

# User inputs
orbit_determination_date = datetime(2025, 3, 15)
tca_date = datetime(2025, 10, 6)

# Earth orbital elements
a_earth = AU
e_earth = 0.0167
i_earth = 0.0
T_earth = 365.25 * 24 * 3600

# Asteroid orbital elements (INPUT)
a_ast = 1.3 * AU                
e_ast = 0.25                    
i_ast = np.radians(10.0)        # inclination (rad)
T_ast = 2 * np.pi * np.sqrt(a_ast**3 / mu_sun)

# time of closest approach (days)
tca_days = (tca_date - orbit_determination_date).days

days_before_tca = 200
animation_days = 365             
dt = 60 * 60 * 24               

# ----------------------------
# Kepler helper functions
# ----------------------------
def kepler_E(M, e, tol=1e-12):
    E = M if e < 0.8 else np.pi
    while True:
        dE = (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
        E -= dE
        if abs(dE) < tol:
            break
    return E

def true_anomaly(E, e):
    return 2 * np.arctan2(np.sqrt(1+e) * np.sin(E/2),
                          np.sqrt(1-e) * np.cos(E/2))

def position_from_elements(a, e, i, T, t_seconds, M0=0.0):
    M = (2*np.pi * (t_seconds / T) + M0) % (2*np.pi)
    E = kepler_E(M, e)
    nu = true_anomaly(E, e)
    r = a * (1 - e**2) / (1 + e * np.cos(nu))
    x_orb = r * np.cos(nu)
    y_orb = r * np.sin(nu)
    x = x_orb
    y = y_orb * np.cos(i)
    z = y_orb * np.sin(i)
    return np.array([x, y, z])

# ----------------------------
# Find M0 that minimizes distance at TCA
# ----------------------------
tca_seconds = tca_days * dt
earth_at_tca = position_from_elements(a_earth, e_earth, i_earth, T_earth, tca_seconds, M0=0.0)

def distance_at_tca(M0):
    ast = position_from_elements(a_ast, e_ast, i_ast, T_ast, tca_seconds, M0)
    return np.linalg.norm(ast - earth_at_tca)

n_grid = 720
M_grid = np.linspace(0, 2*np.pi, n_grid, endpoint=False)
d_grid = np.array([distance_at_tca(M) for M in M_grid])
idx0 = np.argmin(d_grid)
M0_opt = M_grid[idx0]

min_dist_m = distance_at_tca(M0_opt)

print(f"Found M0 (radians) = {M0_opt:.10f}")
print(f"Min distance at TCA = {min_dist_m/1e3:.3f} km (at tca_days = {tca_days})")

# animation timeline
t_start_days = tca_days - days_before_tca
time_days = t_start_days + np.arange(animation_days)   
time_seconds = time_days * dt
num_frames = animation_days

earth_positions = np.array([position_from_elements(a_earth, e_earth, i_earth, T_earth, t, 0.0) for t in time_seconds])
asteroid_positions = np.array([position_from_elements(a_ast, e_ast, i_ast, T_ast, t, M0_opt) for t in time_seconds])

earth_tca_pos = earth_at_tca
asteroid_tca_pos = position_from_elements(a_ast, e_ast, i_ast, T_ast, tca_seconds, M0_opt)

# ----------------------------
# Graphics helpers
# ----------------------------
def create_sphere(center, radius, color, resolution=15):
    u = np.linspace(0, 2*np.pi, resolution)
    v = np.linspace(0, np.pi, resolution)
    x = center[0] + radius * np.outer(np.cos(u), np.sin(v))
    y = center[1] + radius * np.outer(np.sin(u), np.sin(v))
    z = center[2] + radius * np.outer(np.ones_like(u), np.cos(v))
    return go.Surface(x=x, y=y, z=z,
                      colorscale=[[0, color],[1, color]],
                      opacity=0.9, showscale=False, hoverinfo='skip')

sun_sphere = create_sphere([0,0,0], R_sun*30, "yellow")

# ----------------------------
# Initial traces
# ----------------------------
earth_marker0 = go.Scatter3d(x=[earth_positions[0,0]], y=[earth_positions[0,1]], z=[earth_positions[0,2]],
                             mode='markers', marker=dict(size=5, color='blue'), name='Earth')
asteroid_marker0 = go.Scatter3d(x=[asteroid_positions[0,0]], y=[asteroid_positions[0,1]], z=[asteroid_positions[0,2]],
                                mode='markers', marker=dict(size=4, color='red'), name='Asteroid')
earth_traj = go.Scatter3d(x=[], y=[], z=[],
                          mode='lines', line=dict(color='blue'), name='Earth trajectory')
asteroid_traj = go.Scatter3d(x=[], y=[], z=[],
                             mode='lines', line=dict(color='red'), name='Asteroid trajectory')
# placeholder TCA line (keeps legend slot hidden until TCA)
closest_line_placeholder = go.Scatter3d(x=[], y=[], z=[],
                            mode='lines', line=dict(color='green', dash='dot', width=4),
                            name='Line of closest approach', visible=False, showlegend=False)

# Labels initial
sun_label0 = go.Scatter3d(x=[0], y=[0], z=[R_sun*100],
                          mode='text', text=['Sun'],
                          textfont=dict(size=14, color='yellow'),
                          showlegend=False)
earth_label0 = go.Scatter3d(x=[earth_positions[0,0]], y=[earth_positions[0,1]], z=[earth_positions[0,2]+R_earth*2000],
                            mode='text', text=['Earth'],
                            textfont=dict(size=12, color='blue'),
                            showlegend=False)
asteroid_label0 = go.Scatter3d(x=[asteroid_positions[0,0]], y=[asteroid_positions[0,1]], z=[asteroid_positions[0,2]+R_asteroid*2000],
                               mode='text', text=['Asteroid'],
                               textfont=dict(size=12, color='red'),
                               showlegend=False)

# ----------------------------
# Frames
# ----------------------------
frames = []
for k in range(num_frames):
    frame_data = [
        # Sun always drawn
        dict(type='surface', x=sun_sphere.x, y=sun_sphere.y, z=sun_sphere.z,
             showscale=False, opacity=0.9),
        dict(type='scatter3d',
             x=[earth_positions[k,0]], y=[earth_positions[k,1]], z=[earth_positions[k,2]],
             mode='markers', marker=dict(size=5, color='blue'), showlegend=False),
        dict(type='scatter3d',
             x=[asteroid_positions[k,0]], y=[asteroid_positions[k,1]], z=[asteroid_positions[k,2]],
             mode='markers', marker=dict(size=4, color='red'), showlegend=False),
        dict(type='scatter3d',
             x=earth_positions[:k+1,0], y=earth_positions[:k+1,1], z=earth_positions[:k+1,2],
             mode='lines', line=dict(color='blue'), showlegend=False),
        dict(type='scatter3d',
             x=asteroid_positions[:k+1,0], y=asteroid_positions[:k+1,1], z=asteroid_positions[:k+1,2],
             mode='lines', line=dict(color='red'), showlegend=False),
        dict(type='scatter3d',
             x=[0], y=[0], z=[R_sun*100], mode='text', text=['Sun'],
             textfont=dict(size=14, color='yellow'), showlegend=False),
        dict(type='scatter3d',
             x=[earth_positions[k,0]], y=[earth_positions[k,1]], z=[earth_positions[k,2]+R_earth*2000],
             mode='text', text=['Earth'], textfont=dict(size=12, color='blue'), showlegend=False),
        dict(type='scatter3d',
             x=[asteroid_positions[k,0]], y=[asteroid_positions[k,1]], z=[asteroid_positions[k,2]+R_asteroid*2000],
             mode='text', text=['Asteroid'], textfont=dict(size=12, color='red'), showlegend=False)
    ]
    if time_days[k] >= tca_days:
        frame_data.append(dict(
            type='scatter3d',
            x=[earth_tca_pos[0], asteroid_tca_pos[0]],
            y=[earth_tca_pos[1], asteroid_tca_pos[1]],
            z=[earth_tca_pos[2], asteroid_tca_pos[2]],
            mode='lines',
            line=dict(color='green', dash='dot', width=4),
            name='Line of closest approach',
            showlegend=True,
            visible=True
        ))
    frames.append(go.Frame(data=frame_data, name=str(k)))

# ----------------------------
# Layout (legend moved left)
# ----------------------------
axis_range = 2 * AU
layout = go.Layout(
    title=f"Sun-Earth-Asteroid (TCA day = {tca_days}; starts at day {t_start_days})",
    width=1000, height=850,
    scene=dict(
        xaxis=dict(title="X (m)", range=[-axis_range, axis_range], backgroundcolor='black', gridcolor='gray', color='white'),
        yaxis=dict(title="Y (m)", range=[-axis_range, axis_range], backgroundcolor='black', gridcolor='gray', color='white'),
        zaxis=dict(title="Z (m)", range=[-axis_range, axis_range], backgroundcolor='black', gridcolor='gray', color='white'),
        aspectmode='cube'
    ),
    paper_bgcolor='black',
    plot_bgcolor='black',
    font=dict(color='white'),
    showlegend=True,
    legend=dict(
        x=0,  # left side
        y=1,  # top
        xanchor="left",
        yanchor="top",
        bgcolor="rgba(0,0,0,0)",
        font=dict(color="white")
    ),
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
        steps=[dict(method='animate',
                    args=[[str(k)], dict(mode='immediate',
                                        frame=dict(duration=0, redraw=True),
                                        transition=dict(duration=0))],
                    label=str(int(time_days[k]))) for k in range(num_frames)],
        active=0,
        x=0.1, y=0,
        currentvalue=dict(prefix='Day: ')
    )]
)

# ----------------------------
# Initial data
# ----------------------------
initial_data = [
    dict(type='surface', x=sun_sphere.x, y=sun_sphere.y, z=sun_sphere.z, showscale=False, opacity=0.9),
    earth_traj, asteroid_traj,
    earth_marker0, asteroid_marker0,
    sun_label0, earth_label0, asteroid_label0,
    closest_line_placeholder
]

fig = go.Figure(data=initial_data, layout=layout, frames=frames)

# Show and save
fig.show()
fig.write_html("asteroid_simulation.html")

print(f"\nSummary:")
print(f"Asteroid orbital inputs: a = {a_ast/AU:.6f} AU, e = {e_ast:.6f}, i = {np.degrees(i_ast):.4f} deg")
print(f"TCA (days) = {tca_days}")
print(f"Found M0 (rad) = {M0_opt:.10f}")
print(f"Minimum distance at TCA = {min_dist_m/1e3:.3f} km")

def simulate_sun_earth_asteroid(
    asteroid_obj: Optional[Dict[str, Any]] = None,
    *,
    num_steps: int = 365,
    compat: bool = False,
) -> str:
    """Convenience function kept for backward compatibility.

    Returns a Plotly HTML fragment (not a full HTML page).
    """
    sim = Simulator(num_steps=num_steps)
    return sim.simulate(asteroid_obj=asteroid_obj, compat=compat)
