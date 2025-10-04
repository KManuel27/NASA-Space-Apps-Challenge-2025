import plotly.graph_objs as go
import plotly.io as pio
import numpy as np
from typing import Any, Dict, List, Optional

# Module-level public API
__all__ = ["Simulator", "simulate_sun_earth_asteroid"]


# Physical constants and defaults grouped in a namespace-like dict
DEFAULTS = {
    "G": 6.67430e-11,
    "M_sun": 1.989e30,
    "M_earth": 5.972e24,
    "R_sun": 6.9634e8,
    "R_earth": 6.371e6,
    "R_asteroid": 5e5,
    "AU": 1.496e11,
    "a_earth": 1.496e11,
    "e_earth": 0.0167,
    "T_earth": 365.25 * 24 * 3600,
}


class Simulator:
    """Simulate a simplified Sun-Earth-asteroid three-body system and
    produce an interactive Plotly HTML fragment.

    Usage:
      sim = Simulator(num_steps=365)
      html = sim.simulate(asteroid_obj=None)

    The class is intentionally self-contained and does not run heavy
    computations on import; call `simulate` (or the convenience function
    `simulate_sun_earth_asteroid`) to run.
    """

    def __init__(self, num_steps: int = 365, dt: float = 60 * 60 * 24, defaults: Dict[str, float] = DEFAULTS):
        self.num_steps = int(num_steps)
        self.dt = float(dt)
        # physical parameters
        self.G = defaults["G"]
        self.M_sun = defaults["M_sun"]
        self.M_earth = defaults["M_earth"]
        self.R_sun = defaults["R_sun"]
        self.R_earth = defaults["R_earth"]
        self.R_asteroid = defaults["R_asteroid"]
        self.AU = defaults["AU"]
        self.a_earth = defaults["a_earth"]
        self.e_earth = defaults["e_earth"]
        self.T_earth = defaults["T_earth"]

        # derived
        self.mu_sun = self.G * self.M_sun

        # state arrays (initialized in precompute)
        self.earth_pos: Optional[np.ndarray] = None
        self.earth_vel: Optional[np.ndarray] = None
        self.asteroid_pos: Optional[np.ndarray] = None
        self.asteroid_vel: Optional[np.ndarray] = None

    # ---------------- Kepler helpers ----------------
    @staticmethod
    def kepler_E(M: float, e: float, tol: float = 1e-8) -> float:
        E = M if e < 0.8 else np.pi
        while True:
            dE = (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
            E -= dE
            if abs(dE) < tol:
                break
        return E

    @staticmethod
    def true_anomaly(E: float, e: float) -> float:
        return 2 * np.arctan2(np.sqrt(1 + e) * np.sin(E / 2), np.sqrt(1 - e) * np.cos(E / 2))

    # ---------------- Orbit precomputation ----------------
    def precompute_earth_orbit(self) -> None:
        """Precompute Earth's position and velocity arrays for the simulation."""
        n = self.num_steps
        self.earth_pos = np.zeros((n, 3))
        self.earth_vel = np.zeros((n, 3))

        for i in range(n):
            t = i * self.dt
            M = 2 * np.pi * (t / self.T_earth)
            E = self.kepler_E(M, self.e_earth)
            nu = self.true_anomaly(E, self.e_earth)
            r = self.a_earth * (1 - self.e_earth ** 2) / (1 + self.e_earth * np.cos(nu))
            x = r * np.cos(nu)
            y = r * np.sin(nu)
            self.earth_pos[i] = [x, y, 0]
            v = np.sqrt(self.mu_sun * (2 / r - 1 / self.a_earth))
            vx = -v * np.sin(nu)
            vy = v * np.cos(nu)
            self.earth_vel[i] = [vx, vy, 0]

    # ---------------- Initialization ----------------
    def init_asteroid_default(self) -> None:
        """Create default asteroid initial conditions near Earth."""
        n = self.num_steps
        self.asteroid_pos = np.zeros((n, 3))
        self.asteroid_vel = np.zeros((n, 3))

        r_ae = 4 * self.R_earth * 1e3
        v_circ_ae = np.sqrt(self.G * self.M_earth / r_ae)
        ast_pos_rel = np.array([r_ae, 0, 0])
        ast_vel_rel = np.array([0, v_circ_ae, 0])

        # default: place relative to first Earth position/velocity
        self.asteroid_pos[0] = self.earth_pos[0] + ast_pos_rel
        self.asteroid_vel[0] = self.earth_vel[0] + ast_vel_rel

    def try_init_from_asteroid_obj(self, asteroid_obj: Dict[str, Any]) -> None:
        """If a NeoWs-like asteroid object is provided, try to set
        the initial asteroid state from its close approach data.
        This mutates the [0] element of asteroid_pos/vel when successful.
        """
        if asteroid_obj is None:
            return
        try:
            cad = None
            for a in asteroid_obj.get("close_approach_data", []) or []:
                if str(a.get("orbiting_body", "")).lower() == "earth":
                    cad = a
                    break
            if not cad:
                return
            miss_km = float(cad.get("miss_distance", {}).get("kilometers", np.nan))
            rel_kps = float(cad.get("relative_velocity", {}).get("kilometers_per_second", np.nan))
            if np.isfinite(miss_km):
                miss_m = miss_km * 1000.0
                self.asteroid_pos[0] = self.earth_pos[0] + np.array([miss_m, 0, 0])
            if np.isfinite(rel_kps):
                rel_ms = rel_kps * 1000.0
                self.asteroid_vel[0] = self.earth_vel[0] + np.array([0, rel_ms, 0])
        except Exception:
            # silent fallback to the default initial conditions
            pass

    # ---------------- Propagation ----------------
    def propagate(self) -> None:
        """Simple forward-Euler propagation including Sun and Earth gravity on the asteroid.
        Earth is also propagated under the Sun's gravity (simplified)."""
        if self.earth_pos is None or self.earth_vel is None:
            raise RuntimeError("Call precompute_earth_orbit() before propagate().")
        if self.asteroid_pos is None or self.asteroid_vel is None:
            raise RuntimeError("Call init_asteroid_default() before propagate().")

        sun_pos = np.zeros(3)
        n = self.num_steps
        for i in range(1, n):
            # Earth under Sun
            r_sun_earth = sun_pos - self.earth_pos[i - 1]
            dist_sun_earth = np.linalg.norm(r_sun_earth)
            acc_earth = self.mu_sun * r_sun_earth / dist_sun_earth ** 3
            self.earth_vel[i] = self.earth_vel[i - 1] + acc_earth * self.dt
            self.earth_pos[i] = self.earth_pos[i - 1] + self.earth_vel[i] * self.dt

            # Asteroid: Sun + Earth gravity
            r_sun_ast = sun_pos - self.asteroid_pos[i - 1]
            dist_sun_ast = np.linalg.norm(r_sun_ast)
            acc_sun_ast = self.mu_sun * r_sun_ast / dist_sun_ast ** 3

            r_earth_ast = self.earth_pos[i - 1] - self.asteroid_pos[i - 1]
            dist_earth_ast = np.linalg.norm(r_earth_ast)
            # protect against division by zero
            if dist_earth_ast == 0:
                acc_earth_ast = np.zeros(3)
            else:
                acc_earth_ast = self.G * self.M_earth * r_earth_ast / dist_earth_ast ** 3

            acc_ast = acc_sun_ast + acc_earth_ast
            self.asteroid_vel[i] = self.asteroid_vel[i - 1] + acc_ast * self.dt
            self.asteroid_pos[i] = self.asteroid_pos[i - 1] + self.asteroid_vel[i] * self.dt

    # ---------------- Plot helpers ----------------
    @staticmethod
    def create_sphere(center: List[float], radius: float, color: str, resolution: int = 15) -> go.Surface:
        u = np.linspace(0, 2 * np.pi, resolution)
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
            hoverinfo="skip",
            name="Sun",
        )

    def build_figure(self) -> go.Figure:
        """Build the Plotly figure from precomputed state arrays."""
        if self.earth_pos is None or self.asteroid_pos is None:
            raise RuntimeError("Simulation state not initialized. Run precompute/init/propagate first.")

        # --- Static Sun ---
        sun_sphere = self.create_sphere([0, 0, 0], self.R_sun * 30, "yellow")

        # --- Dynamic objects (start state) ---
        earth_marker = go.Scatter3d(
            x=[self.earth_pos[0, 0]], y=[self.earth_pos[0, 1]], z=[self.earth_pos[0, 2]],
            mode="markers", marker=dict(size=5, color="blue"), name="Earth",
        )
        asteroid_marker = go.Scatter3d(
            x=[self.asteroid_pos[0, 0]], y=[self.asteroid_pos[0, 1]], z=[self.asteroid_pos[0, 2]],
            mode="markers", marker=dict(size=4, color="red"), name="Asteroid",
        )
        earth_traj = go.Scatter3d(
            x=[self.earth_pos[0, 0]],
            y=[self.earth_pos[0, 1]],
            z=[self.earth_pos[0, 2]],
            mode="lines",
            line=dict(color="blue"),
            name="Earth trajectory",
        )

        asteroid_traj = go.Scatter3d(
            x=[self.asteroid_pos[0, 0]],
            y=[self.asteroid_pos[0, 1]],
            z=[self.asteroid_pos[0, 2]],
            mode="lines",
            line=dict(color="red"),
            name="Asteroid trajectory",
        )

        # --- Labels (initial frame) ---
        sun_label = go.Scatter3d(
            x=[0],
            y=[0],
            z=[self.R_sun * 100],
            mode="text",
            text=["Sun"],
            textfont=dict(size=14, color="yellow"),
            showlegend=False,
        )

        earth_label = go.Scatter3d(
            x=[self.earth_pos[0, 0]],
            y=[self.earth_pos[0, 1]],
            z=[self.earth_pos[0, 2] + self.R_earth * 2000],
            mode="text",
            text=["Earth"],
            textfont=dict(size=12, color="blue"),
            showlegend=False,
        )

        asteroid_label = go.Scatter3d(
            x=[self.asteroid_pos[0, 0]],
            y=[self.asteroid_pos[0, 1]],
            z=[self.asteroid_pos[0, 2] + self.R_asteroid * 2000],
            mode="text",
            text=["Asteroid"],
            textfont=dict(size=12, color="red"),
            showlegend=False,
        )

        # --- Frames ---
        frames = []
        for k in range(1, self.num_steps):
            frames.append(
                go.Frame(
                    data=[
                        dict(
                            type="scatter3d",
                            x=[self.earth_pos[k, 0]],
                            y=[self.earth_pos[k, 1]],
                            z=[self.earth_pos[k, 2]],
                        ),
                        dict(
                            type="scatter3d",
                            x=[self.asteroid_pos[k, 0]],
                            y=[self.asteroid_pos[k, 1]],
                            z=[self.asteroid_pos[k, 2]],
                        ),
                        dict(
                            type="scatter3d",
                            x=self.earth_pos[:k, 0],
                            y=self.earth_pos[:k, 1],
                            z=self.earth_pos[:k, 2],
                        ),
                        dict(
                            type="scatter3d",
                            x=self.asteroid_pos[:k, 0],
                            y=self.asteroid_pos[:k, 1],
                            z=self.asteroid_pos[:k, 2],
                        ),
                        dict(type="surface", x=sun_sphere.x, y=sun_sphere.y, z=sun_sphere.z),
                        dict(
                            type="scatter3d",
                            x=[0],
                            y=[0],
                            z=[self.R_sun * 100],
                            text=["Sun"],
                        ),
                        dict(
                            type="scatter3d",
                            x=[self.earth_pos[k, 0]],
                            y=[self.earth_pos[k, 1]],
                            z=[self.earth_pos[k, 2] + self.R_earth * 2000],
                            text=["Earth"],
                        ),
                        dict(
                            type="scatter3d",
                            x=[self.asteroid_pos[k, 0]],
                            y=[self.asteroid_pos[k, 1]],
                            z=[self.asteroid_pos[k, 2] + self.R_asteroid * 2000],
                            text=["Asteroid"],
                        ),
                    ],
                    name=str(k),
                )
            )

        axis_range = 2 * self.AU
        layout = go.Layout(
            title="Sun-Earth-Asteroid System",
            width=900,
            height=800,
            scene=dict(
                xaxis=dict(range=[-axis_range, axis_range], backgroundcolor="black", gridcolor="gray"),
                yaxis=dict(range=[-axis_range, axis_range], backgroundcolor="black", gridcolor="gray"),
                zaxis=dict(range=[-axis_range, axis_range], backgroundcolor="black", gridcolor="gray"),
                aspectmode="cube",
            ),
            paper_bgcolor="black",
            plot_bgcolor="black",
            font=dict(color="white"),
            updatemenus=[
                dict(
                    type="buttons",
                    showactive=False,
                    y=1.05,
                    x=1.2,
                    buttons=[
                        dict(
                            label="Play",
                            method="animate",
                            args=[
                                None,
                                {
                                    "frame": {"duration": 50, "redraw": True},
                                    "fromcurrent": True,
                                    "transition": {"duration": 0},
                                },
                            ],
                        ),
                        dict(
                            label="Pause",
                            method="animate",
                            args=[[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}],
                        ),
                    ],
                )
            ],

            # build slider steps in a readable multi-line form
            sliders=[
                dict(
                    steps=[
                        dict(
                            method="animate",
                            args=[[str(k)], dict(mode="immediate", frame=dict(duration=0, redraw=True))],
                            label=str(k),
                        )
                        for k in range(self.num_steps)
                    ],
                    active=0,
                    x=0.1,
                    y=0,
                    currentvalue=dict(prefix="Step: "),
                )
            ],
        )

        fig = go.Figure(
            data=[
                earth_marker,
                asteroid_marker,
                earth_traj,
                asteroid_traj,
                sun_sphere,
                sun_label,
                earth_label,
                asteroid_label,
            ],
            layout=layout,
            frames=frames,
        )
        return fig

    def build_figure_legacy(self) -> go.Figure:
        """Construct the figure using the original script's style/ordering.

        This attempts to mirror the original procedural implementation as
        closely as possible so visual output matches the prior version.
        """
        # reuse the same objects but construct data in exactly the same order
        sun_sphere = self.create_sphere([0, 0, 0], self.R_sun * 30, "yellow")

        earth_marker = go.Scatter3d(
            x=[self.earth_pos[0, 0]], y=[self.earth_pos[0, 1]], z=[self.earth_pos[0, 2]],
            mode="markers", marker=dict(size=5, color="blue"), name="Earth",
        )
        asteroid_marker = go.Scatter3d(
            x=[self.asteroid_pos[0, 0]], y=[self.asteroid_pos[0, 1]], z=[self.asteroid_pos[0, 2]],
            mode="markers", marker=dict(size=4, color="red"), name="Asteroid",
        )
        earth_traj = go.Scatter3d(
            x=[self.earth_pos[0, 0]],
            y=[self.earth_pos[0, 1]],
            z=[self.earth_pos[0, 2]],
            mode="lines",
            line=dict(color="blue"),
            name="Earth trajectory",
        )

        asteroid_traj = go.Scatter3d(
            x=[self.asteroid_pos[0, 0]],
            y=[self.asteroid_pos[0, 1]],
            z=[self.asteroid_pos[0, 2]],
            mode="lines",
            line=dict(color="red"),
            name="Asteroid trajectory",
        )

        sun_label = go.Scatter3d(
            x=[0],
            y=[0],
            z=[self.R_sun * 100],
            mode="text",
            text=["Sun"],
            textfont=dict(size=14, color="yellow"),
            showlegend=False,
        )

        earth_label = go.Scatter3d(
            x=[self.earth_pos[0, 0]],
            y=[self.earth_pos[0, 1]],
            z=[self.earth_pos[0, 2] + self.R_earth * 2000],
            mode="text",
            text=["Earth"],
            textfont=dict(size=12, color="blue"),
            showlegend=False,
        )

        asteroid_label = go.Scatter3d(
            x=[self.asteroid_pos[0, 0]],
            y=[self.asteroid_pos[0, 1]],
            z=[self.asteroid_pos[0, 2] + self.R_asteroid * 2000],
            mode="text",
            text=["Asteroid"],
            textfont=dict(size=12, color="red"),
            showlegend=False,
        )

        frames = []
        for k in range(1, self.num_steps):
            frames.append(go.Frame(
                data=[
                        dict(
                            type="scatter3d",
                            x=[self.earth_pos[k, 0]],
                            y=[self.earth_pos[k, 1]],
                            z=[self.earth_pos[k, 2]],
                        ),
                        dict(
                            type="scatter3d",
                            x=[self.asteroid_pos[k, 0]],
                            y=[self.asteroid_pos[k, 1]],
                            z=[self.asteroid_pos[k, 2]],
                        ),
                        dict(
                            type="scatter3d",
                            x=self.earth_pos[:k, 0],
                            y=self.earth_pos[:k, 1],
                            z=self.earth_pos[:k, 2],
                        ),
                        dict(
                            type="scatter3d",
                            x=self.asteroid_pos[:k, 0],
                            y=self.asteroid_pos[:k, 1],
                            z=self.asteroid_pos[:k, 2],
                        ),
                        dict(
                            type="surface",
                            x=sun_sphere.x,
                            y=sun_sphere.y,
                            z=sun_sphere.z,
                        ),
                        dict(
                            type="scatter3d",
                            x=[0],
                            y=[0],
                            z=[self.R_sun * 100],
                            text=["Sun"],
                        ),
                        dict(
                            type="scatter3d",
                            x=[self.earth_pos[k, 0]],
                            y=[self.earth_pos[k, 1]],
                            z=[self.earth_pos[k, 2] + self.R_earth * 2000],
                            text=["Earth"],
                        ),
                        dict(
                            type="scatter3d",
                            x=[self.asteroid_pos[k, 0]],
                            y=[self.asteroid_pos[k, 1]],
                            z=[self.asteroid_pos[k, 2] + self.R_asteroid * 2000],
                            text=["Asteroid"],
                        ),
                ],
                name=str(k)
            ))

        axis_range = 2 * self.AU
        layout = go.Layout(
            title="Sun-Earth-Asteroid System",
            width=900, height=800,
            scene=dict(
                xaxis=dict(range=[-axis_range, axis_range], backgroundcolor="black", gridcolor="gray"),
                yaxis=dict(range=[-axis_range, axis_range], backgroundcolor="black", gridcolor="gray"),
                zaxis=dict(range=[-axis_range, axis_range], backgroundcolor="black", gridcolor="gray"),
                aspectmode="cube"
            ),
            paper_bgcolor="black",
            plot_bgcolor="black",
            font=dict(color="white"),
            updatemenus=[dict(
                type="buttons", showactive=False, y=1.05, x=1.2,
                buttons=[
                    dict(
                        label="Play",
                        method="animate",
                        args=[
                            None,
                            {
                                "frame": {"duration": 50, "redraw": True},
                                "fromcurrent": True,
                                "transition": {"duration": 0},
                            },
                        ],
                    ),
                    dict(label="Pause", method="animate", args=[
                        [None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}
                        ])
                ]
            )],
            sliders=[dict(
                steps=[dict(method="animate", args=[
                    [str(k)], dict(mode="immediate", frame=dict(duration=0, redraw=True))
                    ], label=str(k)) for k in range(self.num_steps)],
                active=0, x=0.1, y=0,
                currentvalue=dict(prefix="Step: ")
            )]
        )

        fig = go.Figure(
            data=[
                earth_marker,
                asteroid_marker,
                earth_traj,
                asteroid_traj,
                sun_sphere,
                sun_label,
                earth_label,
                asteroid_label,
            ],
            layout=layout,
            frames=frames,
        )
        return fig

    def simulate(self, asteroid_obj: Optional[Dict[str, Any]] = None, compat: bool = False) -> str:
        """Run the full pipeline and return the Plotly HTML fragment."""
        # compute Earth orbit
        self.precompute_earth_orbit()

        # setup asteroid
        self.init_asteroid_default()
        # try to override with real data if provided
        if asteroid_obj:
            self.try_init_from_asteroid_obj(asteroid_obj)

        # propagate
        self.propagate()

        # build the figure and return HTML div
        if compat:
            fig = self.build_figure_legacy()
        else:
            fig = self.build_figure()
        return pio.to_html(fig, full_html=False)


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
