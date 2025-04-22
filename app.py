import os
from flask import (
    Flask, request, render_template, jsonify,
    redirect, session, url_for
)
from flask_cors import CORS
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from backend import (
    get_video_id,
    fetch_transcript_yta,
    fetch_transcript_yt_dlp,
    fetch_transcript_gdata_oauth,
    generate_fact_check
)


app = Flask(__name__, template_folder="templates")
# Replace with a secure random secret, or set via env var
app.secret_key = os.environ.get("FLASK_SECRET", "change_me_secret")
CORS(app)

# OAuth2 settings
SCOPES = [
    "openid", "email", "profile",
    "https://www.googleapis.com/auth/youtube.readonly"
]
CLIENT_CONFIG = {
    "web": {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [os.environ["OAUTH2_REDIRECT_URI"]],
    }
}


@app.route("/")
def index():
    """Render the single‑page UI."""
    logged_in = "credentials" in session
    user_email = session.get("user", {}).get("email")
    return render_template(
        "index.html",
        logged_in=logged_in,
        email=user_email
    )


@app.route("/login")
def login():
    """Start the Google OAuth2 flow."""
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=os.environ["OAUTH2_REDIRECT_URI"]
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true"
    )
    session["state"] = flow.state
    return redirect(auth_url)


@app.route("/oauth2callback")
def oauth2callback():
    """OAuth2 callback endpoint—save credentials and user info in session."""
    state = session.pop("state", None)
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        state=state,
        redirect_uri=os.environ["OAUTH2_REDIRECT_URI"]
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials

    # Store minimal credentials in session
    session["credentials"] = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }

    # Fetch user's email
    oauth2 = build("oauth2", "v2", credentials=creds)
    userinfo = oauth2.userinfo().get().execute()
    session["user"] = userinfo

    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/fact-check", methods=["POST"])
def fact_check():
    """
    Receives JSON { url: "...youtube.com/watch?v=..." }.
    Returns { result: "<json-string>" } or { error: "..."}.
    """
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify(error="No URL provided"), 400

    vid = get_video_id(url)
    if not vid:
        return jsonify(error="Invalid YouTube URL"), 400

    # 1) Try youtube-transcript-api
    transcript = fetch_transcript_yta(vid)

    # 2) If logged in, try OAuth2 YouTube Data API
    if not transcript and "credentials" in session:
        creds = Credentials(**session["credentials"])
        transcript = fetch_transcript_gdata_oauth(creds, vid)

    # 3) Fallback to yt-dlp
    if not transcript:
        transcript = fetch_transcript_yt_dlp(url)

    if not transcript:
        return jsonify(error="Transcript unavailable"), 404

    # 4) Fact‑check via Vertex AI
    try:
        result = generate_fact_check(transcript)
        return jsonify(result=result)
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route("/debug")
def debug():
    return jsonify({
        "status": "ok",
        "oauth_logged_in": "credentials" in session,
        "user": session.get("user")
    })


if __name__ == "__main__":
    # On GCP Cloud Run, $PORT will be set.
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
