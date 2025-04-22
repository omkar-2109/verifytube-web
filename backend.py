import re
import os
import subprocess
import io

from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai


def get_video_id(url: str) -> str | None:
    """Extract the 11‑char video ID from various YouTube URL forms."""
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    return match.group(1) if match else None


def fetch_transcript_yta(video_id: str) -> str | None:
    """Try the youtube_transcript_api (auto & hi fallback)."""
    try:
        data = YouTubeTranscriptApi.get_transcript(video_id, languages=["en-US"])
        return " ".join(item["text"] for item in data)
    except TranscriptsDisabled:
        return None
    except Exception:
        # fallback Hindi auto subtitles
        try:
            data = YouTubeTranscriptApi.get_transcript(video_id, languages=["hi"])
            return " ".join(item["text"] for item in data)
        except Exception:
            return None


def fetch_transcript_yt_dlp(url: str) -> str | None:
    """
    Fallback via yt-dlp’s auto-subtitles. Downloads .vtt and returns its text.
    """
    vid = get_video_id(url)
    if not vid:
        return None

    out_vtt = f"{vid}.en.vtt"
    cmd = [
        "yt-dlp",
        "--write-auto-sub",
        "--sub-lang", "en",
        "--skip-download",
        "--output", f"{vid}.en.%(ext)s",
        url
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.isfile(out_vtt):
            return open(out_vtt, "r", encoding="utf-8").read().strip()
    except Exception:
        pass

    return None


def fetch_transcript_gdata_oauth(credentials, video_id: str) -> str | None:
    """
    Use an OAuth‑authorized YouTube Data API client to download the caption track.
    """
    youtube = build("youtube", "v3", credentials=credentials)
    resp = youtube.captions().list(part="snippet", videoId=video_id).execute()
    items = resp.get("items", [])
    if not items:
        return None

    caption_id = items[0]["id"]
    request = youtube.captions().download(id=caption_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    return fh.getvalue().decode("utf-8")


def generate_fact_check(transcript: str) -> str:
    """
    Call Vertex AI / Gemini to extract claims & verdicts as JSON.
    """
    # Make sure to set GOOGLE_CLOUD_PROJECT env var to your GCP project ID.
    genai.configure(
        api_key=None,
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location="us-central1",
    )
    prompt = f\"\"\"
You are a fact‑checking AI. Extract ONLY the news‑related claims from the transcript below,
verify each claim’s accuracy, and return a JSON object:

  {{
    "claims": ["claim1", "claim2", …],
    "verdicts": ["true"/"false"/"misleading"/…]
  }}

Transcript:
---
{transcript}
---
\"\"\"
    client = genai.Client()
    contents = [
        genai.types.Content(
            role="user",
            parts=[genai.types.Part.from_text(prompt)]
        )
    ]
    tools = [genai.types.Tool(google_search=genai.types.GoogleSearch())]
    config = genai.types.GenerateContentConfig(
        temperature=0,
        top_p=1,
        max_output_tokens=2048,
        response_modalities=["TEXT"],
        tools=tools,
        system_instruction=[genai.types.Part.from_text("You are a precise fact‑checker.")]
    )

    out = ""
    for chunk in client.models.generate_content_stream(
        model="gemini-2.5-pro-exp-03-25",
        contents=contents,
        config=config
    ):
        if chunk.candidates:
            out += chunk.text
    return out.strip()
