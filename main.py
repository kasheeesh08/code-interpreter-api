from fastapi import FastAPI
from pydantic import BaseModel
import os
from google import genai
from youtube_transcript_api import YouTubeTranscriptApi

app = FastAPI()

class AskRequest(BaseModel):
    video_url: str
    topic: str


def get_video_id(url: str):
    return url.split("v=")[-1] if "v=" in url else url.split("/")[-1]


@app.post("/ask")
def ask(req: AskRequest):
    try:
        video_id = get_video_id(req.video_url)

        # ✅ GET TRANSCRIPT (NO DOWNLOAD → NO BOT BLOCK)
        transcript = YouTubeTranscriptApi.get_transcript(video_id)

        text = " ".join([t["text"] for t in transcript])

        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

        prompt = f"""
Find the FIRST timestamp where this topic appears.

Topic: "{req.topic}"

Transcript:
{text}

Rules:
- Return ONLY timestamp
- Format MUST be HH:MM:SS
"""

        response = client.models.generate_content(
            model="gemini-1.5-pro",
            contents=prompt
        )

        return {
            "timestamp": response.text.strip(),
            "video_url": req.video_url,
            "topic": req.topic
        }

    except Exception as e:
        return {"error": str(e)}