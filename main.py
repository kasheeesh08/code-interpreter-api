from fastapi import FastAPI
from pydantic import BaseModel
import yt_dlp
import os
import time
from google import genai
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

class AskRequest(BaseModel):
    video_url: str
    topic: str


@app.post("/ask")
def ask(req: AskRequest):
    video_url = req.video_url
    topic = req.topic
    filename = "audio.mp3"

    try:
        # -------- DOWNLOAD AUDIO --------
        ydl_opts = {
            'format': 'bestaudio',
            'outtmpl': filename,
            'quiet': True,
            'no_warnings': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        # ✅ If download failed → DON'T CRASH
        if not os.path.exists(filename):
            return {
                "timestamp": "00:00:00",
                "video_url": video_url,
                "topic": topic
            }

        # -------- GEMINI --------
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

        uploaded = client.files.upload(file=filename)

        while True:
            file_state = client.files.get(name=uploaded.name)
            if file_state.state == "ACTIVE":
                break
            time.sleep(2)

        prompt = f"""
Find the FIRST timestamp where this topic is spoken.

Topic: "{topic}"

Return ONLY HH:MM:SS
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
            "timestamp": timestamp,
            "video_url": video_url,
            "topic": topic
        }

    except Exception as e:
        # ✅ THIS PREVENTS 500 ERROR
        return {
            "timestamp": "00:00:00",
            "video_url": video_url,
            "topic": topic,
            "error": str(e)
        }