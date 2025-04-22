# backend.py
import os
import re
import json
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

# Vertex AI / Gemini config via env‐vars
GENAI_PROJECT  = os.environ.get("GCP_PROJECT",  "skillful-cider-451510-j7")
GENAI_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")

def get_video_id(url: str) -> str | None:
    """Extract the 11‑char YouTube ID from any common URL form."""
    m = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url)
    return m[1] if m else None

def get_transcript(video_id: str) -> str | None:
    """
    Fetch any available transcript (manual or auto) via youtube‐transcript‐api.
    Returns a single concatenated string, or None if unavailable.
    """
    try:
        subs = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(item["text"] for item in subs)
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        print(f"[WARN] No transcript for {video_id}: {e}")
        return None
    except Exception as e:
        print(f"[ERROR] Transcript fetch error for {video_id}: {e}")
        return None

def generate_fact_check(transcript: str) -> dict:
    """
    Send transcript into Gemini for fact‐checking.
    Expects JSON output of the form {"claims":[…],"verdicts":[…]}.
    """
    client = genai.Client(
        vertexai=True,
        project=skillful-cider-451510-j7,
        location=us-central1,
    )

    prompt = f"""
You are a fact‐checking AI. Extract ONLY news‐related claims from the transcript below,
verify them, and output EXACTLY a JSON object:

{{
  "claims": ["claim1", "claim2", …],
  "verdicts": ["true", "false", "misleading", …]
}}

Transcript:
\"\"\"{transcript}\"\"\"
"""
    contents = [genai.types.Content(role="user",
                                    parts=[genai.types.Part.from_text(prompt)])]
    tools  = [genai.types.Tool(google_search=genai.types.GoogleSearch())]
    config = genai.types.GenerateContentConfig(
        temperature=0,
        top_p=1,
        seed=0,
        max_output_tokens=4096,
        response_modalities=["TEXT"],
        tools=tools,
        system_instruction=[genai.types.Part.from_text("You are a precise fact‐checker.")]
    )

    out = ""
    for chunk in client.models.generate_content_stream(
            model="gemini-2.5-pro-exp-03-25",
            contents=contents,
            config=config):
        out += chunk.text

    # parse JSON
    try:
        return json.loads(out.strip())
    except Exception as e:
        raise ValueError(f"AI output is not valid JSON: {e}\n---\n{out}")
