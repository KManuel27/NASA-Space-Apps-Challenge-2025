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
    G = 6.67430e-11  # gravitational constant
    M_sun = 1.989e30
    M_earth = 5.972e24
    R_sun = 6.9634e8
    R_earth = 6.371e6
    R_asteroid = 5e5  # For visualization
    AU = 1.496e11

    num_steps = 365
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

    collision_step = None
    impact_lat = None
    impact_lon = None

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

        if collision_step is None and dist_earth_ast <= R_earth:
            collision_step = i
            impact_vector = asteroid_pos[i] - earth_pos[i]
            x, y, z = impact_vector
            r = np.linalg.norm(impact_vector)
            lat = np.arcsin(z / r) * 180 / np.pi
            lon = np.arctan2(y, x) * 180 / np.pi
            impact_lat = lat
            impact_lon = lon
            print(f"Collision at step {i}, Lat: {lat:.2f}°, Lon: {lon:.2f}°")
            break

    # TEXTURE URL (earth map)
    earth_texture_url = 'https://raw.githubusercontent.com/plotly/datasets/master/earth.jpg'

    def create_sphere(center, radius, color, opacity=0.9, resolution=30, texture_url=None):
        u = np.linspace(0, 2 * np.pi, resolution)
        v = np.linspace(0, np.pi, resolution)
        x = center[0] + radius * np.outer(np.cos(u), np.sin(v))
        y = center[1] + radius * np.outer(np.sin(u), np.sin(v))
        z = center[2] + radius * np.outer(np.ones_like(u), np.cos(v))

        if texture_url:
            return go.Surface(
                x=x, y=y, z=z,
                surfacecolor=np.tile(np.linspace(0, 1, resolution), (resolution, 1)),
                colorscale='Earth',
                cmin=0, cmax=1,
                showscale=False,
                opacity=opacity,
                hoverinfo='skip'
            )
        else:
            return go.Surface(
                x=x, y=y, z=z,
                colorscale=[[0, color], [1, color]],
                opacity=opacity,
                showscale=False,
                hoverinfo='skip'
            )

    def create_earth_grid(center, radius, res=20):
        lon_lines = []
        for lon_deg in np.linspace(-180, 180, 12):
            lon = np.radians(lon_deg)
            theta = np.linspace(0, np.pi, res)
            x = np.array(center[0] + radius * np.cos(lon) * np.sin(theta)).flatten()
            y = np.array(center[1] + radius * np.sin(lon) * np.sin(theta)).flatten()
            z = np.array(center[2] + radius * np.cos(theta)).flatten()
            lon_lines.append(go.Scatter3d(
                x=x, y=y, z=z, mode='lines',
                line=dict(color='black', width=1),
                hoverinfo='skip',
                showlegend=False   # prevent from showing in legend
            ))
        lat_lines = []
        for lat_deg in np.linspace(-90, 90, 9):
            lat = np.radians(lat_deg)
            phi = np.linspace(-np.pi, np.pi, res)
            x = np.array(center[0] + radius * np.cos(lat) * np.cos(phi)).flatten()
            y = np.array(center[1] + radius * np.cos(lat) * np.sin(phi)).flatten()
            z = np.array(center[2] + radius * np.sin(lat)).flatten()
            lat_lines.append(go.Scatter3d(
                x=x, y=y, z=z, mode='lines',
                line=dict(color='black', width=1),
                hoverinfo='skip',
                showlegend=False   # prevent from showing in legend
            ))
        return lon_lines + lat_lines

    sun_sphere = create_sphere([0,0,0], R_sun*50, 'yellow')

    max_frame = collision_step if collision_step else num_steps - 1

    frames = []
    for step in range(max_frame+1):
        earth_sphere = create_sphere(earth_pos[step], R_earth*500, 'blue', texture_url=earth_texture_url)
        asteroid_sphere = create_sphere(asteroid_pos[step], R_asteroid*500, 'red', resolution=10)
        earth_grid_lines = create_earth_grid(earth_pos[step], R_earth*500)

        earth_traj = go.Scatter3d(
            x=earth_pos[:step+1,0], y=earth_pos[:step+1,1], z=earth_pos[:step+1,2],
            mode='lines', line=dict(color='blue'), name='Earth trajectory'
        )
        asteroid_traj = go.Scatter3d(
            x=asteroid_pos[:step+1,0], y=asteroid_pos[:step+1,1], z=asteroid_pos[:step+1,2],
            mode='lines', line=dict(color='red'), name='Asteroid trajectory'
        )

        labels = [
            go.Scatter3d(x=[0], y=[0], z=[0], mode='text', text=["Sun"], textfont=dict(size=14, color='yellow'), showlegend=False),
            go.Scatter3d(x=[earth_pos[step][0]], y=[earth_pos[step][1]], z=[earth_pos[step][2]+R_earth*1000],
                        mode='text', text=["Earth"], textfont=dict(size=12, color='blue'), showlegend=False),
            go.Scatter3d(x=[asteroid_pos[step][0]], y=[asteroid_pos[step][1]], z=[asteroid_pos[step][2]+R_asteroid*1000],
                        mode='text', text=["Asteroid"], textfont=dict(size=12, color='red'), showlegend=False)
        ]

        frame_data = [sun_sphere, earth_sphere, asteroid_sphere, earth_traj, asteroid_traj] + earth_grid_lines + labels
        frames.append(go.Frame(data=frame_data, name=str(step)))

    # Initial display
    data = frames[0].data

    axis_range = 1.5 * AU
    layout = go.Layout(
        title="Sun-Earth-Asteroid System",
        width=1000, height=900,
        scene=dict(
            xaxis=dict(range=[-axis_range, axis_range], gridcolor='black', backgroundcolor='black'),
            yaxis=dict(range=[-axis_range, axis_range], gridcolor='black', backgroundcolor='black'),
            zaxis=dict(range=[-axis_range, axis_range], gridcolor='black', backgroundcolor='black'),
            aspectmode='cube'
        ),
        updatemenus=[dict(
            type='buttons', showactive=False, y=1.1, x=1.3,
            buttons=[
                dict(label='Play', method='animate', args=[None, {"frame": {"duration": 30, "redraw": True},
                                                                "fromcurrent": True, "transition": {"duration": 0}}]),
                dict(label='Pause', method='animate', args=[[None], {"frame": {"duration": 0, "redraw": False},
                                                                    "mode": "immediate", "transition": {"duration": 0}}])
            ])
        ],
        sliders=[dict(
            steps=[dict(method='animate', args=[[str(k)], dict(mode='immediate',
                                                            frame=dict(duration=0, redraw=True),
                                                            transition=dict(duration=0))],
                        label=str(k)) for k in range(max_frame+1)],
            active=0, transition=dict(duration=0),
            x=0.1, y=0, currentvalue=dict(prefix='Step: ')
        )]
    )

    fig = go.Figure(data=data, layout=layout, frames=frames)

    # Convert Plotly figure to HTML div
    graph_html = pio.to_html(fig, full_html=False)

    # Pass the graph to the template
    return render_template("list.html", graph_html=graph_html)

if __name__ == "__main__":
    app.run(debug=True)
