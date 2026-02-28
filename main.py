from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import sys
from io import StringIO
import traceback
import os

from google import genai
from google.genai import types

app = FastAPI()

# Enable CORS
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------- Request Model --------
class CodeRequest(BaseModel):
    code: str


# -------- Tool Function --------
def execute_python_code(code: str) -> dict:
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        exec(code)
        output = sys.stdout.getvalue()
        return {"success": True, "output": output}

    except Exception:
        output = traceback.format_exc()
        return {"success": False, "output": output}

    finally:
        sys.stdout = old_stdout


# -------- AI Structured Output --------
class ErrorAnalysis(BaseModel):
    error_lines: List[int]


def analyze_error_with_ai(code: str, tb: str) -> List[int]:
    try:
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

        prompt = f"""
Analyze Python code and traceback.
Return exact line numbers where error occurred.

CODE:
{code}

TRACEBACK:
{tb}
"""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "error_lines": types.Schema(
                            type=types.Type.ARRAY,
                            items=types.Schema(type=types.Type.INTEGER)
                        )
                    },
                    required=["error_lines"]
                )
            )
        )

        if not response.text:
            return [1]

        result = ErrorAnalysis.model_validate_json(response.text)
        return result.error_lines

    except Exception as e:
        print("AI ERROR:", e)
        return [1]


# -------- Endpoint --------
@app.post("/code-interpreter")
def code_interpreter(req: CodeRequest):
    execution = execute_python_code(req.code)

    if execution["success"]:
        return {
            "error": [],
            "result": execution["output"]
        }

    error_lines = analyze_error_with_ai(req.code, execution["output"])

    return {
        "error": error_lines,
        "result": execution["output"]
    }