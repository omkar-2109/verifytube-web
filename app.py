import os
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from backend import (
    get_video_id,
    fetch_transcript_yta,
    fetch_transcript_gdata,
    fetch_transcript_yt_dlp,
    generate_fact_check,
)

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/fact-check', methods=['POST'])
def fact_check():
    data = request.json or {}
    url = data.get('url','').strip()
    if not url:
        return jsonify(error='No URL provided'), 400

    vid = get_video_id(url)
    if not vid:
        return jsonify(error='Invalid YouTube URL'), 400

    # 1) try youtube‑transcript‑api
    transcript = fetch_transcript_yta(vid)
    # 2) fallback to Data API (only snippet metadata)
    if not transcript:
        transcript = fetch_transcript_gdata(vid)
    # 3) fallback to yt-dlp
    if not transcript:
        transcript = fetch_transcript_yt_dlp(url)
    if not transcript:
        return jsonify(error='Transcript unavailable'), 404

    # fact‑check
    try:
        result_json = generate_fact_check(transcript)
        return jsonify(result=result_json)
    except Exception as e:
        return jsonify(error=str(e)), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
