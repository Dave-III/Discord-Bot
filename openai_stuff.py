from pathlib import Path
from openai import OpenAI
import os
from dotenv import load_dotenv
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def transcribe_audio(path: str) -> str:
    with open(path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
        )
    return result.text

def chat_reply(user_text: str, system_prompt: str = "You are a helpful assistant.") -> str:
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        max_tokens=200,
    )
    return resp.choices[0].message.content.strip()

def tts_to_file(text: str, out_path: str):
    out = Path(out_path)

    with client.audio.speech.with_streaming_response.create(
        model="gpt-4o-mini-tts",
        voice="alloy",
        input=text,

    ) as response:
        response.stream_to_file(out)