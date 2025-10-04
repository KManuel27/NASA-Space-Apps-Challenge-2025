from flask import Flask, render_template
import plotly.graph_objs as go
import plotly.io as pio
import numpy as np

app = Flask(__name__)

# --------------- Page 1: Static Start Page --------------
@app.route("/")
def start_page():
    return render_template("startPage.html")  # No Python computation yet

# --------------- Page 2: Meteor Visualization ---------------
@app.route("/meteors")
def meteor_list(): #ORBITAL MECHANICS AND VISUALISATION CODE:

    # Constants
    G = 6.67430e-11
    M_sun = 1.989e30
    M_earth = 5.972e24
    R_sun = 6.9634e8
    R_earth = 6.371e6
    R_asteroid = 5e5
    AU = 1.496e11

    num_steps = 365   # one year (daily steps)
    dt = 60 * 60 * 24  # 24 hours

    a_earth = AU
    e_earth = 0.0167
    T_earth = 365.25 * 24 * 3600
    mu_sun = G * M_sun

    def kepler_E(M, e, tol=1e-8):
        E = M if e < 0.8 else np.pi
        while True:
            dE = (E - e*np.sin(E) - M) / (1 - e*np.cos(E))
            E -= dE
            if abs(dE) < tol:
                break
        return E

    def true_anomaly(E, e):
        return 2*np.arctan2(np.sqrt(1+e)*np.sin(E/2), np.sqrt(1-e)*np.cos(E/2))

    # Precompute Earth orbit
    earth_pos = np.zeros((num_steps, 3))
    earth_vel = np.zeros((num_steps, 3))

    for i in range(num_steps):
        t = i * dt
        M = 2*np.pi*(t / T_earth)
        E = kepler_E(M, e_earth)
        nu = true_anomaly(E, e_earth)
        r = a_earth*(1 - e_earth**2) / (1 + e_earth*np.cos(nu))
        x = r * np.cos(nu)
        y = r * np.sin(nu)
        earth_pos[i] = [x, y, 0]
        v = np.sqrt(mu_sun*(2/r - 1/a_earth))
        vx = -v * np.sin(nu)
        vy = v * np.cos(nu)
        earth_vel[i] = [vx, vy, 0]

    # Asteroid initial condition
    r_ae = 4 * R_earth * 1e3
    v_circ_ae = np.sqrt(G * M_earth / r_ae)
    ast_pos_rel = np.array([r_ae, 0, 0])
    ast_vel_rel = np.array([0, v_circ_ae, 0])

    asteroid_pos = np.zeros((num_steps, 3))
    asteroid_vel = np.zeros((num_steps, 3))
    asteroid_pos[0] = earth_pos[0] + ast_pos_rel
    asteroid_vel[0] = earth_vel[0] + ast_vel_rel
    sun_pos = np.zeros(3)

    # Propagation loop
    for i in range(1, num_steps):
        r_sun_earth = sun_pos - earth_pos[i-1]
        dist_sun_earth = np.linalg.norm(r_sun_earth)
        acc_earth = mu_sun * r_sun_earth / dist_sun_earth**3
        earth_vel[i] = earth_vel[i-1] + acc_earth * dt
        earth_pos[i] = earth_pos[i-1] + earth_vel[i] * dt

        r_sun_ast = sun_pos - asteroid_pos[i-1]
        dist_sun_ast = np.linalg.norm(r_sun_ast)
        acc_sun_ast = mu_sun * r_sun_ast / dist_sun_ast**3

        r_earth_ast = earth_pos[i-1] - asteroid_pos[i-1]
        dist_earth_ast = np.linalg.norm(r_earth_ast)
        acc_earth_ast = G * M_earth * r_earth_ast / dist_earth_ast**3

        acc_ast = acc_sun_ast + acc_earth_ast
        asteroid_vel[i] = asteroid_vel[i-1] + acc_ast * dt
        asteroid_pos[i] = asteroid_pos[i-1] + asteroid_vel[i] * dt

    # --- Plotting helpers ---
    def create_sphere(center, radius, color, resolution=15):
        u = np.linspace(0, 2*np.pi, resolution)
        v = np.linspace(0, np.pi, resolution)
        x = center[0] + radius * np.outer(np.cos(u), np.sin(v))
        y = center[1] + radius * np.outer(np.sin(u), np.sin(v))
        z = center[2] + radius * np.outer(np.ones_like(u), np.cos(v))
        return go.Surface(
            x=x, y=y, z=z,
            colorscale=[[0, color], [1, color]],
            opacity=0.9, showscale=False,
            hoverinfo="skip", name="Sun"
        )

    # --- Static Sun ---
    sun_sphere = create_sphere([0,0,0], R_sun*30, "yellow")

    # --- Dynamic objects (start state) ---
    earth_marker = go.Scatter3d(
        x=[earth_pos[0,0]], y=[earth_pos[0,1]], z=[earth_pos[0,2]],
        mode="markers", marker=dict(size=5, color="blue"), name="Earth"
    )
    asteroid_marker = go.Scatter3d(
        x=[asteroid_pos[0,0]], y=[asteroid_pos[0,1]], z=[asteroid_pos[0,2]],
        mode="markers", marker=dict(size=4, color="red"), name="Asteroid"
    )
    earth_traj = go.Scatter3d(
        x=[earth_pos[0,0]], y=[earth_pos[0,1]], z=[earth_pos[0,2]],
        mode="lines", line=dict(color="blue"), name="Earth trajectory"
    )
    asteroid_traj = go.Scatter3d(
        x=[asteroid_pos[0,0]], y=[asteroid_pos[0,1]], z=[asteroid_pos[0,2]],
        mode="lines", line=dict(color="red"), name="Asteroid trajectory"
    )

    # --- Labels (initial frame) ---
    sun_label = go.Scatter3d(
        x=[0], y=[0], z=[R_sun*100], mode="text", text=["Sun"],
        textfont=dict(size=14, color="yellow"), showlegend=False
    )
    earth_label = go.Scatter3d(
        x=[earth_pos[0,0]], y=[earth_pos[0,1]], z=[earth_pos[0,2]+R_earth*2000],
        mode="text", text=["Earth"], textfont=dict(size=12, color="blue"), showlegend=False
    )
    asteroid_label = go.Scatter3d(
        x=[asteroid_pos[0,0]], y=[asteroid_pos[0,1]], z=[asteroid_pos[0,2]+R_asteroid*2000],
        mode="text", text=["Asteroid"], textfont=dict(size=12, color="red"), showlegend=False
    )

    # --- Frames ---
    frames = []
    for k in range(1, num_steps):
        frames.append(go.Frame(
            data=[
                dict(type="scatter3d", x=[earth_pos[k,0]], y=[earth_pos[k,1]], z=[earth_pos[k,2]]),    # Earth marker
                dict(type="scatter3d", x=[asteroid_pos[k,0]], y=[asteroid_pos[k,1]], z=[asteroid_pos[k,2]]), # Asteroid marker
                dict(type="scatter3d", x=earth_pos[:k,0], y=earth_pos[:k,1], z=earth_pos[:k,2]),      # Earth traj
                dict(type="scatter3d", x=asteroid_pos[:k,0], y=asteroid_pos[:k,1], z=asteroid_pos[:k,2]), # Asteroid traj
                dict(type="surface", x=sun_sphere.x, y=sun_sphere.y, z=sun_sphere.z),  # Sun
                dict(type="scatter3d", x=[0], y=[0], z=[R_sun*100], text=["Sun"]),   # Sun label
                dict(type="scatter3d", x=[earth_pos[k,0]], y=[earth_pos[k,1]], z=[earth_pos[k,2]+R_earth*2000], text=["Earth"]),
                dict(type="scatter3d", x=[asteroid_pos[k,0]], y=[asteroid_pos[k,1]], z=[asteroid_pos[k,2]+R_asteroid*2000], text=["Asteroid"])
            ],
            name=str(k)
        ))

    # --- Layout ---
    axis_range = 2 * AU
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
                dict(label="Play", method="animate",
                    args=[None, {"frame": {"duration": 50, "redraw": True},
                                "fromcurrent": True, "transition": {"duration": 0}}]),
                dict(label="Pause", method="animate",
                    args=[[None], {"frame": {"duration": 0, "redraw": False},
                                    "mode": "immediate"}])
            ]
        )],
        sliders=[dict(
            steps=[dict(method="animate", args=[[str(k)], dict(mode="immediate",
                                                            frame=dict(duration=0, redraw=True))],
                        label=str(k)) for k in range(num_steps)],
            active=0, x=0.1, y=0,
            currentvalue=dict(prefix="Step: ")
        )]
    )

    # --- Figure ---
    fig = go.Figure(
        data=[earth_marker, asteroid_marker, earth_traj, asteroid_traj, sun_sphere,
            sun_label, earth_label, asteroid_label],
        layout=layout, frames=frames
    )

    # Convert Plotly figure to HTML div
    graph_html = pio.to_html(fig, full_html=False)

    # Pass the graph to the template
    return render_template("list.html", graph_html=graph_html)

if __name__ == "__main__":
    app.run(debug=True)