import os
import google.generativeai as genai
from flask import Flask, request, render_template, jsonify
from flask_cors import CORS

from backend import (
    get_video_id,
    fetch_transcript_yta,
    fetch_transcript_gdata,
    fetch_transcript_yt_dlp,
    generate_fact_check
)

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/fact-check', methods=['POST'])
def fact_check():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify(error='No URL provided'), 400

    vid = get_video_id(url)
    if not vid:
        return jsonify(error='Invalid YouTube URL'), 400

    # Try methods in order
    transcript = fetch_transcript_yta(vid)
    if not transcript:
        transcript = fetch_transcript_gdata(vid)
    if not transcript:
        transcript = fetch_transcript_yt_dlp(url)
    if not transcript:
        return jsonify(error='Transcript unavailable'), 404

    try:
        result = generate_fact_check(transcript)
        return jsonify(result=result)
    except Exception as e:
        return jsonify(error=str(e)), 500


@app.route('/debug', methods=['GET'])
def debug():
    return jsonify({
        'status': 'ok',
        'youtube_api_key': bool(os.environ.get('YOUTUBE_API_KEY')),
        'genai_configured': hasattr(genai, 'Client')
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
