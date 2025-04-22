import re
import os
import subprocess
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
from googleapiclient.discovery import build
import google.generativeai as genai


def get_video_id(url: str) -> str | None:
    """Extract a YouTube video ID from full URL."""
    match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
    return match.group(1) if match else None


def fetch_transcript_yta(video_id: str) -> str | None:
    """Try YouTubeTranscriptApi (official transcript)."""
    try:
        entries = YouTubeTranscriptApi.get_transcript(video_id, languages=['en-US'])
        return ' '.join(e['text'] for e in entries)
    except TranscriptsDisabled:
        return None
    except Exception:
        # fallback to any automatic language
        try:
            entries = YouTubeTranscriptApi.get_transcript(video_id, languages=['hi'])
            return ' '.join(e['text'] for e in entries)
        except Exception:
            return None


def fetch_transcript_yt_dlp(url: str) -> str | None:
    """Fallback: use yt-dlp to download auto-captions."""
    vid = get_video_id(url)
    if not vid:
        return None
    vtt_file = f'{vid}.en.vtt'
    cmd = [
        'yt-dlp',
        '--write-auto-sub',
        '--sub-lang', 'en',
        '--skip-download',
        '--output', f'{vid}.en.%(ext)s',
        url
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.isfile(vtt_file):
            return open(vtt_file, 'r', encoding='utf-8').read()
    except Exception:
        pass
    return None


def fetch_transcript_gdata(video_id: str) -> str | None:
    """
    List captions via YouTube Data API.
    (NOTE: downloading caption body via API key alone is not supported.)
    """
    api_key = os.environ.get('YOUTUBE_API_KEY')
    if not api_key:
        return None

    yt = build('youtube', 'v3', developerKey=api_key)
    resp = yt.captions().list(part='snippet', videoId=video_id).execute()
    items = resp.get('items', [])
    if not items:
        return None
    # cannot download actual caption track with API key only
    return None


def generate_fact_check(transcript: str) -> str:
    """
    Call Vertex AI (Gemini) to fact‑check the transcript.
    Returns a raw JSON‑ish string.
    """
    # Configure via Application Default Credentials or GOOGLE_APPLICATION_CREDENTIALS
    genai.configure(api_key=None)

    client = genai.Client(
        vertexai=True,
        project=os.environ.get('GOOGLE_CLOUD_PROJECT'),
        location='us-central1'
    )

    prompt = f"""
You are a fact‑checking AI. Extract only news‑related claims from the transcript below, verify each, 
and output JSON with two arrays: "claims" and "verdicts".

Transcript:
\"\"\"{transcript}\"\"\"
"""
    contents = [
        genai.types.Content(
            role='user',
            parts=[genai.types.Part.from_text(prompt)]
        )
    ]
    tools = [genai.types.Tool(google_search=genai.types.GoogleSearch())]
    config = genai.types.GenerateContentConfig(
        temperature=0,
        top_p=1,
        max_output_tokens=2048,
        response_modalities=['TEXT'],
        tools=tools,
        system_instruction=[genai.types.Part.from_text('You are a precise fact‑checker.')]
    )

    out = ''
    for chunk in client.models.generate_content_stream(
        model='gemini-2.5-pro-exp-03-25',
        contents=contents,
        config=config
    ):
        if chunk.candidates:
            out += chunk.text
    return out.strip()
