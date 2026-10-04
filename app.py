from flask import Flask, request, render_template
from preferences import save_preferences, load_preferences

app = Flask(__name__)

# This decorator tells Flask: when someone visits /settings, run the function below.
# methods=["GET", "POST"] allows it to load the page (GET) and handle form submits (POST).
@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        # Pull the values entered/selected by the user in the HTML form
        data = {
            "video_type": request.form.get("video_type"),
            "audience": request.form.get("audience"),
            "tone": request.form.get("tone"),
            "goal": request.form.get("goal"),
            # getlist() gets all selected values for the platform checkboxes
            "platforms": request.form.getlist("platforms")
        }
        # Save the dictionary to preferences.json
        save_preferences(data)
    
    # Load whatever is currently saved in preferences.json and send it to the page
    current = load_preferences()
    return render_template("settings.html", prefs=current)

if __name__ == "__main__":
    app.run(debug=True)