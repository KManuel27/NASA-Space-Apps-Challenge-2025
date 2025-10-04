meteors = [
    {"name": "Meteor A", "size": "10m", "speed": "20 km/s", "description": "A small meteor"},
    {"name": "Meteor B", "size": "50m", "speed": "15 km/s", "description": "Medium meteor"},
]

import json

with open("meteors.json", "w") as f:
    json.dump(meteors, f)