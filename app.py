# app.py
import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from backend import get_video_id, get_transcript, generate_fact_check

app = Flask(__name__)
# allow your browser (or extension) if you still need CORS:
CORS(app, origins="*")


@app.route("/", methods=["GET", "POST"])
def index():
    error      = None
    transcript = None
    claims     = []
    verdicts   = []
    url        = ""

    if request.method == "POST":
        url = (request.form.get("url") or "").strip()
        if not url:
            error = "Please enter a YouTube URL."
        else:
            vid = get_video_id(url)
            if not vid:
                error = "Invalid YouTube URL."
            else:
                transcript = get_transcript(vid)
                if not transcript:
                    error = "Transcript unavailable for this video."
                else:
                    try:
                        payload = generate_fact_check(transcript)
                        claims   = payload.get("claims", [])
                        verdicts = payload.get("verdicts", [])
                    except ValueError as ve:
                        error = f"Fact‑check JSON error: {ve}"
                    except Exception as ex:
                        error = f"Internal error: {ex}"

    return render_template(
        "index.html",
        url=url,
        error=error,
        transcript=transcript,
        claims=claims,
        verdicts=verdicts,
    )


@app.route("/fact-check", methods=["POST"])
def api_fact_check():
    """
    Optional: keep your JSON API endpoint for AJAX or external clients.
    """
    data = request.get_json() or {}
    url  = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    vid = get_video_id(url)
    if not vid:
        return jsonify({"error": "Invalid YouTube URL"}), 400

    transcript = get_transcript(vid)
    if not transcript:
        return jsonify({"error": "Transcript unavailable"}), 404

    try:
        return jsonify(generate_fact_check(transcript)), 200
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 500
    except Exception as ex:
        return jsonify({"error": f"Internal error: {ex}"}), 500


if __name__ == "__main__":
    port  = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
