import re
import os
import subprocess
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
from googleapiclient.discovery import build
import google.generativeai as genai

def get_video_id(url: str) -> str | None:
    m = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11}).*', url)
    return m.group(1) if m else None

def fetch_transcript_yta(video_id: str) -> str | None:
    try:
        subs = YouTubeTranscriptApi.get_transcript(video_id, languages=['en-US'])
        return ' '.join([e['text'] for e in subs])
    except TranscriptsDisabled:
        return None
    except:
        try:
            subs = YouTubeTranscriptApi.get_transcript(video_id, languages=['hi'])
            return ' '.join([e['text'] for e in subs])
        except:
            return None

def fetch_transcript_yt_dlp(url: str) -> str | None:
    """Fallback via yt-dlp auto‑subtitles."""
    fn = 'subtitles.txt'
    cmd = [
        'yt-dlp', '--write-auto-sub', '--sub-lang', 'en',
        '--skip-download', '--output', '%(id)s.vtt', url
    ]
    try:
        subprocess.run(cmd, check=True)
        vid = get_video_id(url)
        with open(f'{vid}.en.vtt', 'r', encoding='utf-8') as f:
            text = f.read()
        return text
    except:
        return None

def fetch_transcript_gdata(video_id: str) -> str | None:
    """Use YouTube Data API to get captions list (body download needs OAuth2)."""
    key = os.environ.get('YOUTUBE_API_KEY')
    if not key:
        return None
    yt = build('youtube', 'v3', developerKey=key)
    resp = yt.captions().list(part='snippet', videoId=video_id).execute()
    items = resp.get('items', [])
    if not items:
        return None
    # NOTE: downloading caption body via API key alone is not supported.
    return None

def generate_fact_check(transcript: str) -> str:
    genai.configure(api_key=None)              # use ADC or GOOGLE_APPLICATION_CREDENTIALS
    client = genai.Client(
      vertexai=True,
      project=os.environ.get('GOOGLE_CLOUD_PROJECT'),
      location='us-central1'
    )

    prompt = f"""
You are a fact‑checking AI. Extract only news‑related claims from the transcript below, verify each claim, 
and respond in JSON with two arrays: "claims" and "verdicts".
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
    cfg = genai.types.GenerateContentConfig(
      temperature=0,
      top_p=1,
      max_output_tokens=2048,
      tools=tools,
      response_modalities=['TEXT'],
      system_instruction=[genai.types.Part.from_text('You are a precise fact-checker.')]
    )

    out = ''
    for chunk in client.models.generate_content_stream(
      model='gemini-2.5-pro-exp-03-25',
      contents=contents,
      config=cfg
    ):
        if chunk.candidates:
            out += chunk.text
    return out.strip()
