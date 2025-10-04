from flask import Flask, render_template, request, redirect, url_for
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
    # default range: one month ago -> today
    today = date.today()
    one_month_ago = today - timedelta(days=30)

    # allow overriding via query params
    start = request.args.get('start_date', one_month_ago.isoformat())
    end = request.args.get('end_date', today.isoformat())

    asteroids = []
    error = None
    try:
        asteroids = neoWs.get_hazardous_asteroids(start, end)
    except Exception as e:
        error = str(e)

    # render the template and inject initial data for the JS
    return render_template("availableMeteors.html", start_date=start, end_date=end, asteroids=asteroids, error=error)

# --------------- Page 2: Meteor Visualization ---------------
@app.route("/meteors")
def meteor_list():  # ORBITAL MECHANICS AND VISUALISATION CODE:
    # Legacy route (not used directly). Redirect to visualization UI.
    return redirect(url_for('start_page'))


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

if __name__ == "__main__":
    app.run(debug=True)
