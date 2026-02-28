from fastapi import FastAPI
from pydantic import BaseModel
import yt_dlp
import os
import time
from google import genai

app = FastAPI()

class AskRequest(BaseModel):
    video_url: str
    topic: str


@app.post("/ask")
def ask(req: AskRequest):
    try:
        video_url = req.video_url
        topic = req.topic

        filename = "audio.mp3"

        # -------- DOWNLOAD AUDIO (FIXED) --------
        ydl_opts = {
            'format': 'bestaudio',
            'outtmpl': filename,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
            }],
            'quiet': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        # -------- GEMINI CLIENT --------
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

        # -------- UPLOAD FILE --------
        uploaded = client.files.upload(file=filename)

        # -------- WAIT UNTIL ACTIVE --------
        while True:
            file_state = client.files.get(name=uploaded.name)
            if file_state.state == "ACTIVE":
                break
            time.sleep(2)

        # -------- PROMPT (FIXED) --------
        prompt = f"""
Find the FIRST timestamp where this topic is spoken.

Topic: "{topic}"

Rules:
- Return ONLY timestamp
- Format: HH:MM:SS
- No explanation
"""

        response = client.models.generate_content(
            model="gemini-1.5-pro",
            contents=[uploaded, prompt]
        )

        timestamp = response.text.strip()

        # -------- CLEANUP --------
        if os.path.exists(filename):
            os.remove(filename)

        return {
            "timestamp": timestamp
        }

    except Exception as e:
        return {
            "error": str(e)
        }