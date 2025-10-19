import json, re, traceback, requests, xml.etree.ElementTree as ET
from flask import Flask, request
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    CouldNotRetrieveTranscript
)

app = Flask(__name__)

# ------------------------------------------------------
# Utility
# ------------------------------------------------------
def extract_video_id(url):
    m = re.search(r"(?:v=|youtu\.be/)([0-9A-Za-z_-]{11})", url)
    return m.group(1) if m else None

# ------------------------------------------------------
# Fallback XML fetch
# ------------------------------------------------------
def fetch_timedtext(video_id, lang="en", tlang=None):
    """Fetch captions directly from YouTube timedtext (with full browser headers)."""
    try:
        url = f"https://www.youtube.com/api/timedtext?v={video_id}&lang={lang}"
        if tlang:
            url += f"&tlang={tlang}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/127.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.youtube.com/",
        }
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200 or not r.text.strip():
            print(f"⚠️ timedtext HTTP {r.status_code}")
            return None
        root = ET.fromstring(r.text)
        lines = [t.text for t in root.findall("text") if t.text]
        return " ".join(lines) if lines else None
    except Exception as e:
        print("⚠️ XML fetch failed:", e)
        return None

# ------------------------------------------------------
# Transcript fetch
# ------------------------------------------------------
def fetch_youtube_transcript(video_id):
    languages = ["en", "en-US", "hi", "fr", "es", "de", "ne", "zh-Hans", "zh-Hant"]
    try:
        print(f"🎥 Trying API for {video_id}")
        data = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
        text = " ".join([d["text"] for d in data])
        lang = data[0].get("language", "unknown")
        return text, lang, "YouTubeTranscriptAPI"
    except (TranscriptsDisabled, NoTranscriptFound, CouldNotRetrieveTranscript):
        print("⚠️ Official API failed, falling back to timedtext…")
        for lang in languages:
            text = fetch_timedtext(video_id, lang)
            if text:
                return text, lang, "YouTubeTimedText"
        text = fetch_timedtext(video_id, "auto", "en")
        if text:
            return text, "auto→en", "YouTubeTimedTextTranslated"
        return None, None, "YouTubeRequestFailed"
    except Exception as e:
        traceback.print_exc()
        return None, None, f"Error: {str(e)}"

# ------------------------------------------------------
# Flask routes
# ------------------------------------------------------
@app.route("/transcript", methods=["POST"])
def get_transcript():
    try:
        payload = request.get_json(silent=True)
        if not payload or "url" not in payload:
            return ("Missing YouTube URL", 400)
        vid = extract_video_id(payload["url"])
        if not vid:
            return ("Invalid YouTube URL", 400)
        text, lang, src = fetch_youtube_transcript(vid)
        if not text:
            return (
                json.dumps({"error": "Transcript not available", "source": src}),
                404,
                {"Content-Type": "application/json; charset=utf-8"},
            )
        return (
            json.dumps(
                {"transcript": text, "language_code": lang, "source": src},
                ensure_ascii=False,
            ),
            200,
            {"Content-Type": "application/json; charset=utf-8"},
        )
    except Exception as e:
        traceback.print_exc()
        return (
            json.dumps({"error": str(e), "source": "ServerError"}),
            500,
            {"Content-Type": "application/json; charset=utf-8"},
        )

@app.route("/", methods=["GET"])
def root():
    return "✅ NoteTube Transcript API is live!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
