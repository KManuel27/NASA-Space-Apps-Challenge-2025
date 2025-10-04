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


def create_sphere(center, radius, color, resolution=15):
    u = np.linspace(0, 2*np.pi, resolution)
    v = np.linspace(0, np.pi, resolution)
    x = center[0] + radius * np.outer(np.cos(u), np.sin(v))
    y = center[1] + radius * np.outer(np.sin(u), np.sin(v))
    z = center[2] + radius * np.outer(np.ones_like(u), np.cos(v))
    return go.Surface(
        x=x,
        y=y,
        z=z,
        colorscale=[[0, color], [1, color]],
        opacity=0.9,
        showscale=False,
        hoverinfo='skip',
    )


class Simulator:
    """Encapsulates the sun-earth-asteroid simulation and Plotly figure creation.

    The implementation preserves the original numeric logic but moves it behind an
    object interface so importing this module has no side-effects.
    """

    def __init__(self,
                 orbit_determination_date: datetime = datetime(2025, 3, 15),
                 tca_date: datetime = datetime(2025, 10, 6),
                 days_before_tca: int = 200,
                 animation_days: int = 365,
                 dt: int = 60 * 60 * 24,
                 a_ast: float = 1.3 * AU,
                 e_ast: float = 0.25,
                 i_ast: float = np.radians(10.0)):

        # preserve defaults from the original script
        self.orbit_determination_date = orbit_determination_date
        self.tca_date = tca_date
        self.days_before_tca = days_before_tca
        self.animation_days = animation_days
        self.dt = dt

        # Earth orbital elements (constants)
        self.a_earth = AU
        self.e_earth = 0.0167
        self.i_earth = 0.0
        self.T_earth = 365.25 * 24 * 3600

        # Asteroid orbital elements (inputs)
        self.a_ast = a_ast
        self.e_ast = e_ast
        self.i_ast = i_ast
        self.T_ast = 2 * np.pi * np.sqrt(self.a_ast**3 / mu_sun)

        # compute timeline / TCA
        self.tca_days = (self.tca_date - self.orbit_determination_date).days
        self.tca_seconds = self.tca_days * self.dt

        # find M0 that minimizes the distance at TCA (same grid search)
        self._compute_M0_opt()

        # timeline arrays
        self.t_start_days = self.tca_days - self.days_before_tca
        self.time_days = self.t_start_days + np.arange(self.animation_days)
        self.time_seconds = self.time_days * self.dt
        self.num_frames = self.animation_days

        # positions
        self.earth_positions = np.array([
            position_from_elements(self.a_earth, self.e_earth, self.i_earth, self.T_earth, t, 0.0)
            for t in self.time_seconds
        ])
        self.asteroid_positions = np.array([
            position_from_elements(self.a_ast, self.e_ast, self.i_ast, self.T_ast, t, self.M0_opt)
            for t in self.time_seconds
        ])

        self.earth_tca_pos = position_from_elements(
            self.a_earth,
            self.e_earth,
            self.i_earth,
            self.T_earth,
            self.tca_seconds,
            0.0,
        )
        self.asteroid_tca_pos = position_from_elements(
            self.a_ast,
            self.e_ast,
            self.i_ast,
            self.T_ast,
            self.tca_seconds,
            self.M0_opt,
        )

        # sphere for sun
        self.sun_sphere = create_sphere([0, 0, 0], R_sun * 30, "yellow")

        # build the figure (frames + layout)
        self._build_figure()

    def _compute_M0_opt(self):
        # compute Earth position at TCA for reference
        earth_at_tca = position_from_elements(
            self.a_earth,
            self.e_earth,
            self.i_earth,
            self.T_earth,
            self.tca_seconds,
            M0=0.0,
        )

        def distance_at_tca_local(M0):
            ast = position_from_elements(self.a_ast, self.e_ast, self.i_ast, self.T_ast, self.tca_seconds, M0)
            return np.linalg.norm(ast - earth_at_tca)

        n_grid = 720
        M_grid = np.linspace(0, 2*np.pi, n_grid, endpoint=False)
        d_grid = np.array([distance_at_tca_local(M) for M in M_grid])
        idx0 = np.argmin(d_grid)
        self.M0_opt = M_grid[idx0]
        self.min_dist_m = distance_at_tca_local(self.M0_opt)

    def _build_figure(self):
        # initial traces
        earth_marker0 = go.Scatter3d(
            x=[self.earth_positions[0, 0]],
            y=[self.earth_positions[0, 1]],
            z=[self.earth_positions[0, 2]],
            mode='markers',
            marker=dict(size=5, color='blue'),
            name='Earth',
        )

        asteroid_marker0 = go.Scatter3d(
            x=[self.asteroid_positions[0, 0]],
            y=[self.asteroid_positions[0, 1]],
            z=[self.asteroid_positions[0, 2]],
            mode='markers',
            marker=dict(size=4, color='red'),
            name='Asteroid',
        )

        earth_traj = go.Scatter3d(x=[], y=[], z=[], mode='lines', line=dict(color='blue'), name='Earth trajectory')
        asteroid_traj = go.Scatter3d(x=[], y=[], z=[], mode='lines', line=dict(color='red'), name='Asteroid trajectory')

        closest_line_placeholder = go.Scatter3d(
            x=[],
            y=[],
            z=[],
            mode='lines',
            line=dict(color='green', dash='dot', width=4),
            name='Line of closest approach',
            visible=False,
            showlegend=False,
        )

        sun_label0 = go.Scatter3d(
            x=[0],
            y=[0],
            z=[R_sun * 100],
            mode='text',
            text=['Sun'],
            textfont=dict(size=14, color='yellow'),
            showlegend=False,
        )

        earth_label0 = go.Scatter3d(
            x=[self.earth_positions[0, 0]],
            y=[self.earth_positions[0, 1]],
            z=[self.earth_positions[0, 2] + R_earth * 2000],
            mode='text',
            text=['Earth'],
            textfont=dict(size=12, color='blue'),
            showlegend=False,
        )

        asteroid_label0 = go.Scatter3d(
            x=[self.asteroid_positions[0, 0]],
            y=[self.asteroid_positions[0, 1]],
            z=[self.asteroid_positions[0, 2] + R_asteroid * 2000],
            mode='text',
            text=['Asteroid'],
            textfont=dict(size=12, color='red'),
            showlegend=False,
        )

        frames = []
        for k in range(self.num_frames):
            frame_data = [
                dict(
                    type='surface',
                    x=self.sun_sphere.x,
                    y=self.sun_sphere.y,
                    z=self.sun_sphere.z,
                    showscale=False,
                    opacity=0.9,
                ),
                dict(
                    type='scatter3d',
                    x=[self.earth_positions[k, 0]],
                    y=[self.earth_positions[k, 1]],
                    z=[self.earth_positions[k, 2]],
                    mode='markers',
                    marker=dict(size=5, color='blue'),
                    showlegend=False,
                ),
                dict(
                    type='scatter3d',
                    x=[self.asteroid_positions[k, 0]],
                    y=[self.asteroid_positions[k, 1]],
                    z=[self.asteroid_positions[k, 2]],
                    mode='markers',
                    marker=dict(size=4, color='red'),
                    showlegend=False,
                ),
                dict(
                    type='scatter3d',
                    x=self.earth_positions[: k + 1, 0],
                    y=self.earth_positions[: k + 1, 1],
                    z=self.earth_positions[: k + 1, 2],
                    mode='lines',
                    line=dict(color='blue'),
                    showlegend=False,
                ),
                dict(
                    type='scatter3d',
                    x=self.asteroid_positions[: k + 1, 0],
                    y=self.asteroid_positions[: k + 1, 1],
                    z=self.asteroid_positions[: k + 1, 2],
                    mode='lines',
                    line=dict(color='red'),
                    showlegend=False,
                ),
                dict(
                    type='scatter3d',
                    x=[0],
                    y=[0],
                    z=[R_sun * 100],
                    mode='text',
                    text=['Sun'],
                    textfont=dict(size=14, color='yellow'),
                    showlegend=False,
                ),
                dict(
                    type='scatter3d',
                    x=[self.earth_positions[k, 0]],
                    y=[self.earth_positions[k, 1]],
                    z=[self.earth_positions[k, 2] + R_earth * 2000],
                    mode='text',
                    text=['Earth'],
                    textfont=dict(size=12, color='blue'),
                    showlegend=False,
                ),
                dict(
                    type='scatter3d',
                    x=[self.asteroid_positions[k, 0]],
                    y=[self.asteroid_positions[k, 1]],
                    z=[self.asteroid_positions[k, 2] + R_asteroid * 2000],
                    mode='text',
                    text=['Asteroid'],
                    textfont=dict(size=12, color='red'),
                    showlegend=False,
                ),
            ]
            if self.time_days[k] >= self.tca_days:
                frame_data.append(dict(
                    type='scatter3d',
                    x=[self.earth_tca_pos[0], self.asteroid_tca_pos[0]],
                    y=[self.earth_tca_pos[1], self.asteroid_tca_pos[1]],
                    z=[self.earth_tca_pos[2], self.asteroid_tca_pos[2]],
                    mode='lines',
                    line=dict(color='green', dash='dot', width=4),
                    name='Line of closest approach',
                    showlegend=True,
                    visible=True
                ))
            frames.append(go.Frame(data=frame_data, name=str(k)))

        axis_range = 2 * AU
        layout = go.Layout(
            title=f"Sun-Earth-Asteroid (TCA day = {self.tca_days}; starts at day {self.t_start_days})",
            width=1000, height=850,
            scene=dict(
                xaxis=dict(
                    title="X (m)",
                    range=[-axis_range, axis_range],
                    backgroundcolor='black',
                    gridcolor='gray',
                    color='white',
                ),
                yaxis=dict(
                    title="Y (m)",
                    range=[-axis_range, axis_range],
                    backgroundcolor='black',
                    gridcolor='gray',
                    color='white',
                ),
                zaxis=dict(
                    title="Z (m)",
                    range=[-axis_range, axis_range],
                    backgroundcolor='black',
                    gridcolor='gray',
                    color='white',
                ),
                aspectmode='cube'
            ),
            paper_bgcolor='black',
            plot_bgcolor='black',
            font=dict(color='white'),
            showlegend=True,
            legend=dict(x=0, y=1, xanchor="left", yanchor="top", bgcolor="rgba(0,0,0,0)", font=dict(color="white")),
            updatemenus=[
                dict(
                    type='buttons',
                    showactive=False,
                    y=1.05,
                    x=1.18,
                    buttons=[
                        dict(
                            label='Play',
                            method='animate',
                            args=[
                                None,
                                {
                                    "frame": {"duration": 60, "redraw": True},
                                    "fromcurrent": True,
                                    "transition": {"duration": 0},
                                },
                            ],
                        ),
                        dict(
                            label='Pause',
                            method='animate',
                            args=[
                                [None],
                                {
                                    "frame": {"duration": 0, "redraw": False},
                                    "mode": "immediate",
                                    "transition": {"duration": 0},
                                },
                            ],
                        ),
                    ],
                )
            ],
            sliders=[
                dict(
                    steps=[
                        dict(
                            method='animate',
                            args=[
                                [str(k)],
                                dict(
                                    mode='immediate',
                                    frame=dict(duration=0, redraw=True),
                                    transition=dict(duration=0),
                                ),
                            ],
                            label=str(int(self.time_days[k])),
                        )
                        for k in range(self.num_frames)
                    ],
                    active=0,
                    x=0.1,
                    y=0,
                    currentvalue=dict(prefix='Day: '),
                )
            ],
        )

        initial_data = [
            dict(
                type='surface',
                x=self.sun_sphere.x,
                y=self.sun_sphere.y,
                z=self.sun_sphere.z,
                showscale=False,
                opacity=0.9,
            ),
            earth_traj, asteroid_traj,
            earth_marker0, asteroid_marker0,
            sun_label0, earth_label0, asteroid_label0,
            closest_line_placeholder
        ]

        self.fig = go.Figure(data=initial_data, layout=layout, frames=frames)

    def simulate(self, asteroid_obj: Optional[Dict[str, Any]] = None, *, compat: bool = False) -> str:
        """Return a Plotly HTML fragment for the simulation.

        The method preserves the previous public behaviour: it returns an HTML
        fragment suitable for embedding into a larger template.
        """
        return self.fig.to_html(full_html=False)

    def save_html(self, path: str = "asteroid_simulation.html") -> None:
        self.fig.write_html(path)

    def show(self) -> None:
        self.fig.show()

    def summary_lines(self):
        return [
            "Summary:",
            (
                f"Asteroid orbital inputs: a = {self.a_ast/AU:.6f} AU, "
                f"e = {self.e_ast:.6f}, i = {np.degrees(self.i_ast):.4f} deg"
            ),
            f"TCA (days) = {self.tca_days}",
            f"Found M0 (rad) = {self.M0_opt:.10f}",
            f"Minimum distance at TCA = {self.min_dist_m/1e3:.3f} km"
        ]


def simulate_sun_earth_asteroid(
    asteroid_obj: Optional[Dict[str, Any]] = None,
    *,
    num_steps: int = 365,
    compat: bool = False,
) -> str:
    """Compatibility wrapper: construct a Simulator and return HTML fragment."""
    sim = Simulator()
    return sim.simulate(asteroid_obj=asteroid_obj, compat=compat)


if __name__ == "__main__":
    sim = Simulator()
    # replicate previous behaviour when run as a script
    sim.show()
    sim.save_html("asteroid_simulation.html")
    for line in sim.summary_lines():
        print(line)
