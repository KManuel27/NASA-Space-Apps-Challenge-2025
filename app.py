from flask import Flask, render_template
import meteor_viz

app = Flask(__name__)


# --------------- Page 1: Static Start Page --------------
@app.route("/")
def start_page():
    return render_template("startPage.html")  # No Python computation yet

@app.route("/available_meteors")
def available_meteors():
    # This function will return a list of available meteors
    return render_template("availableMeteors.html")

# --------------- Page 2: Meteor Visualization ---------------
@app.route("/meteors")
def meteor_list():  # ORBITAL MECHANICS AND VISUALISATION CODE:
    graph_html = meteor_viz.simulate_sun_earth_asteroid()
    # Pass the graph to the template
    return render_template("list.html", graph_html=graph_html)


if __name__ == "__main__":
    app.run(debug=True)
