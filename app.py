import os
from datetime import datetime

import psycopg2
from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template, send_from_directory
from psycopg2.extras import Json, RealDictCursor
from preferences import save_preferences, load_preferences

load_dotenv()

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
    return response


def get_db_connection():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(db_url)


def serialize_row(row):
    record = dict(row)
    for key, value in record.items():
        if isinstance(value, datetime):
            record[key] = value.isoformat()
    return record

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


@app.route("/api/projects", methods=["GET", "POST"])
def projects():
    if request.method == "GET":
        try:
            conn = get_db_connection()
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT project_id, user_id, title, created_at, updated_at,
                           job_id, status, raw_video_url
                    FROM projects
                    ORDER BY created_at DESC NULLS LAST, project_id DESC
                    """
                )
                rows = cur.fetchall()
            return jsonify({"projects": [serialize_row(row) for row in rows]})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        finally:
            conn.close()

    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    if user_id is None:
        return jsonify({"error": "user_id is required"}), 400

    title = (data.get("title") or data.get("name") or "").strip() or "Untitled Project"
    job_id = data.get("job_id")
    status = data.get("status") or "PENDING"
    raw_video_url = data.get("raw_video_url")

    try:
        conn = get_db_connection()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO projects (user_id, title, job_id, status, raw_video_url)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING project_id, user_id, title, created_at, updated_at,
                          job_id, status, raw_video_url
                """,
                (user_id, title, job_id, status, raw_video_url),
            )
            row = cur.fetchone()
        conn.commit()
        return jsonify(serialize_row(row)), 201
    except Exception as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 500
    finally:
        conn.close()


@app.route("/api/editor/<int:edit_id>", methods=["GET", "PUT"])
def editor_draft(edit_id):
    try:
        conn = get_db_connection()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    if request.method == "GET":
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT edit_id, clip_id, edit_type, parameters, applied_at
                    FROM edits
                    WHERE edit_id = %s
                    """,
                    (edit_id,),
                )
                row = cur.fetchone()
            if row is None:
                return jsonify({"error": "Edit draft not found"}), 404
            return jsonify(serialize_row(row))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        finally:
            conn.close()

    data = request.get_json(silent=True) or {}
    allowed = ("clip_id", "edit_type", "parameters")
    updates = {key: data[key] for key in allowed if key in data}
    if not updates:
        conn.close()
        return jsonify({
            "error": "Provide at least one of clip_id, edit_type, or parameters"
        }), 400

    edit_type = updates.get("edit_type")
    if "edit_type" in updates and (not isinstance(edit_type, str) or not edit_type.strip()):
        conn.close()
        return jsonify({"error": "edit_type must be a non-empty string"}), 400
    if "edit_type" in updates:
        updates["edit_type"] = edit_type.strip()

    if "parameters" in updates:
        if not isinstance(updates["parameters"], (dict, list)):
            conn.close()
            return jsonify({"error": "parameters must be a JSON object or array"}), 400
        updates["parameters"] = Json(updates["parameters"])

    assignments = [f"{column} = %s" for column in updates]
    values = list(updates.values())
    values.append(edit_id)

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                UPDATE edits
                SET {", ".join(assignments)}, applied_at = CURRENT_TIMESTAMP
                WHERE edit_id = %s
                RETURNING edit_id, clip_id, edit_type, parameters, applied_at
                """,
                values,
            )
            row = cur.fetchone()
        if row is None:
            conn.rollback()
            return jsonify({"error": "Edit draft not found"}), 404
        conn.commit()
        return jsonify(serialize_row(row))
    except Exception as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 500
    finally:
        conn.close()

@app.route('/<path:filename>')
def serve_prototype(filename):
    return send_from_directory('.', filename)


if __name__ == "__main__":
    app.run(debug=True)