import os
import re
import json
import pickle
import hashlib
import secrets
import base64 as b64
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
from bs4 import BeautifulSoup
from flask import Flask, render_template, jsonify, redirect, url_for, session, request, Response, stream_with_context

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", os.urandom(24))

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.pickle"
OTF_SENDER = "OTbeatReport@orangetheoryfitness.com"

SNIPPET_RE = re.compile(
    r"STUDIO WORKOUT SUMMARY\s+"
    r"(.+?)\s+"                                   # location
    r"(\d{2}/\d{2}/\d{4})\s+"                    # date
    r"(\d{1,2}:\d{2}\s+[AP]M)\s+"               # time
    r"(.+?)\s+"                                   # coach
    r"(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+" # zones 1-5
    r"MINUTES\s*/\s*ZONE\s+"
    r"(\d+)\s+CALORIES BURNED\s+"
    r"(\d+)\s+SPLAT POINTS\s+"
    r"(\d+)\s+AVG\.?\s*HEART-RATE\s+Peak HR:\s+"
    r"(\d+)\s+"
    r"(\d+)\s+STEPS"
)

COACH_SYSTEM_PROMPT = """You are an expert OrangeTheory Fitness (OTF) coach reviewing a member's complete workout history.

OTF Context:
- Splat Points = minutes spent in Orange Zone (Z4 "Push") or Red Zone (Z5 "All Out")
- OTF's goal is 12+ splat points per session for the optimal EPOC (afterburn) effect
- Heart rate zones: Gray (Z1 rest), Blue (Z2 warm-up), Green (Z3 base pace), Orange (Z4 push), Red (Z5 all-out)
- Higher avg/peak HR and more orange/red zone time = higher intensity
- A strong session typically has 20+ minutes in Green or above

Analyze the member's JSON workout history and write a coaching report with EXACTLY these 5 bold section headers and content:

**Performance Summary**
2-3 sentences on overall recent performance. Reference specific numbers, dates, and coaches.

**What's Working**
2-3 bullet points on genuine positive patterns you see — by coach, by time of day, recent streaks, zone strengths. Use • for bullets.

**Areas to Watch**
2-3 bullet points on real dips, trends, or warning signs. Be specific — cite actual numbers and dates. Use • for bullets.

**To-Dos**
Numbered list of 3-5 concrete, actionable recommendations for the next 1-2 weeks. Be specific (mention coaches by name, set HR or splat targets, recommend class frequency).

**Encouragement**
One motivating sentence referencing a real achievement from their data (total calories, longest streak, best splat, etc.).

Important: Reference actual data — specific dates, coach names, calorie counts, splat points, HR values. Do not be generic."""


def parse_snippet(snippet):
    clean = snippet.replace("\u200c", "").replace("\u00a0", " ")
    m = SNIPPET_RE.search(clean)
    if not m:
        return None
    return {
        "location": m.group(1),
        "date": m.group(2),
        "time": m.group(3),
        "coach": m.group(4),
        "zone_gray": int(m.group(5)),
        "zone_blue": int(m.group(6)),
        "zone_green": int(m.group(7)),
        "zone_orange": int(m.group(8)),
        "zone_red": int(m.group(9)),
        "calories": int(m.group(10)),
        "splat_points": int(m.group(11)),
        "avg_hr": int(m.group(12)),
        "peak_hr": int(m.group(13)),
        "steps": int(m.group(14)),
    }


def _decode_body(part):
    """Recursively extract HTML (preferred) or plain text from a message part."""
    mime = part.get("mimeType", "")
    data = part.get("body", {}).get("data", "")
    if mime == "text/html" and data:
        return b64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
    for sub in part.get("parts", []):
        result = _decode_body(sub)
        if result:
            return result
    if mime == "text/plain" and data:
        return b64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
    return None


def _soup_text(html):
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ", strip=True)
    # Remove zero-width non-joiners that OTF embeds inside time strings (e.g. "02\u200c:43")
    return text.replace("\u200c", "").replace("\u00a0", " ")


def _float(s):
    try:
        return float(s)
    except Exception:
        return None


def parse_treadmill(text):
    m = re.search(r"TREADMILL PERFORMANCE TOTALS(.+?)(?:ROWER PERFORMANCE|FLOOR PERFORMANCE|$)",
                  text, re.DOTALL | re.IGNORECASE)
    if not m:
        return {}
    t = m.group(1)
    out = {}

    d = re.search(r"([\d.]+)\s*miles\s*Total Distance", t, re.IGNORECASE)
    if d: out["treadmill_miles"] = _float(d.group(1))

    tt = re.search(r"(\d+:\d+)\s*Total Time", t, re.IGNORECASE)
    if tt: out["treadmill_time"] = tt.group(1)

    sp = re.search(r"AVG\.?\s*SPEED\s*([\d.]+)\s*mph\s*Max:\s*([\d.]+)", t, re.IGNORECASE)
    if sp:
        out["treadmill_avg_speed"] = _float(sp.group(1))
        out["treadmill_max_speed"] = _float(sp.group(2))

    inc = re.search(r"AVG\.?\s*INCLINE\s*([\d.]+)\s*%\s*Max:\s*([\d.]+)", t, re.IGNORECASE)
    if inc:
        out["treadmill_avg_incline"] = _float(inc.group(1))
        out["treadmill_max_incline"] = _float(inc.group(2))

    pace = re.search(r"AVG\.?\s*PACE\s*(\d+:\d+)\s*Fastest:\s*(\d+:\d+)", t, re.IGNORECASE)
    if pace:
        out["treadmill_avg_pace"] = pace.group(1)
        out["treadmill_fastest_pace"] = pace.group(2)

    elev = re.search(r"ELEVATION\s*([\d.]+)\s*feet", t, re.IGNORECASE)
    if elev: out["treadmill_elevation"] = _float(elev.group(1))

    return out


def parse_rower(text):
    m = re.search(r"ROWER PERFORMANCE TOTALS(.+?)(?:FLOOR PERFORMANCE|$)",
                  text, re.DOTALL | re.IGNORECASE)
    if not m:
        return {}
    r = m.group(1)
    out = {}

    d = re.search(r"([\d.]+)\s*m\s*Total Distance", r, re.IGNORECASE)
    if d: out["rower_meters"] = _float(d.group(1))

    tt = re.search(r"(\d+:\d+)\s*Total Time", r, re.IGNORECASE)
    if tt: out["rower_time"] = tt.group(1)

    w = re.search(r"AVG\.?\s*WATTAGE\s*([\d.]+)\s*watt\s*Max:\s*([\d.]+)", r, re.IGNORECASE)
    if w:
        out["rower_avg_wattage"] = _float(w.group(1))
        out["rower_max_wattage"] = _float(w.group(2))

    sp = re.search(r"AVG\.?\s*SPEED\s*([\d.]+)\s*km/h\s*Max:\s*([\d.]+)", r, re.IGNORECASE)
    if sp:
        out["rower_avg_speed"] = _float(sp.group(1))
        out["rower_max_speed"] = _float(sp.group(2))

    split = re.search(r"500\s*M\.?\s*SPLIT\s*(\d+:\d+)", r, re.IGNORECASE)
    if split: out["rower_500m_split"] = split.group(1)

    stroke = re.search(r"(?:AVG\.?\s*)?STROKE\s*RATE\s*([\d.]+)", r, re.IGNORECASE)
    if stroke: out["rower_avg_stroke_rate"] = _float(stroke.group(1))

    return out


def get_credentials():
    try:
        from google.auth.transport.requests import Request
    except ImportError:
        return None

    if not os.path.exists(TOKEN_FILE):
        return None

    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, "wb") as f:
                pickle.dump(creds, f)
        except Exception:
            return None

    return creds


def fetch_workouts():
    from googleapiclient.discovery import build

    creds = get_credentials()
    if not creds or not creds.valid:
        return None, "not_authenticated"

    service = build("gmail", "v1", credentials=creds)
    results = []
    page_token = None

    while True:
        kwargs = {"userId": "me", "q": f"from:{OTF_SENDER}", "maxResults": 500}
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.users().messages().list(**kwargs).execute()
        messages = response.get("messages", [])

        for msg in messages:
            msg_data = (
                service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="full")
                .execute()
            )
            parsed = parse_snippet(msg_data.get("snippet", ""))
            if not parsed:
                continue
            html = _decode_body(msg_data.get("payload", {}))
            if html:
                text = _soup_text(html)
                parsed.update(parse_treadmill(text))
                parsed.update(parse_rower(text))
            results.append(parsed)

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    results.sort(key=lambda x: datetime.strptime(x["date"], "%m/%d/%Y"))
    return results, None


@app.route("/")
def index():
    return render_template("index.html")


def pkce_pair():
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = b64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


@app.route("/login")
def login():
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(CREDENTIALS_FILE, scopes=SCOPES)
    flow.redirect_uri = url_for("oauth2callback", _external=True)

    verifier, challenge = pkce_pair()
    session["code_verifier"] = verifier

    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    session["state"] = state
    return redirect(auth_url)


@app.route("/oauth2callback")
def oauth2callback():
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(
        CREDENTIALS_FILE, scopes=SCOPES, state=session.get("state")
    )
    flow.redirect_uri = url_for("oauth2callback", _external=True)
    flow.fetch_token(
        authorization_response=request.url,
        code_verifier=session.pop("code_verifier", None),
    )
    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(flow.credentials, f)
    return redirect(url_for("index"))


@app.route("/api/workouts")
def workouts():
    if not os.path.exists(CREDENTIALS_FILE):
        return jsonify({"error": "no_credentials"}), 401
    data, error = fetch_workouts()
    if error == "not_authenticated":
        return jsonify({"error": "not_authenticated", "login_url": url_for("login")}), 401
    if data is None:
        return jsonify({"error": "Failed to fetch data"}), 500
    return jsonify(data)


@app.route("/api/debug-email")
def debug_email():
    """Return raw extracted text from the most recent OTF email for debugging."""
    from googleapiclient.discovery import build
    creds = get_credentials()
    if not creds or not creds.valid:
        return jsonify({"error": "not_authenticated"}), 401
    service = build("gmail", "v1", credentials=creds)
    resp = service.users().messages().list(userId="me", q=f"from:{OTF_SENDER}", maxResults=1).execute()
    msgs = resp.get("messages", [])
    if not msgs:
        return jsonify({"error": "no messages"})
    msg_data = service.users().messages().get(userId="me", id=msgs[0]["id"], format="full").execute()
    html = _decode_body(msg_data.get("payload", {}))
    text = _soup_text(html) if html else ""
    return jsonify({"text": text, "snippet": msg_data.get("snippet", "")})


@app.route("/api/coach-insights", methods=["POST"])
def coach_insights():
    try:
        import anthropic
    except ImportError:
        return jsonify({"error": "anthropic package not installed"}), 500

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not set"}), 500

    body = request.get_json(silent=True) or {}
    workout_data = body.get("workouts", [])
    if not workout_data:
        return jsonify({"error": "No workout data provided"}), 400

    user_message = (
        "Here is my complete OTF workout history (oldest to newest). "
        "Please analyze it and give me your coaching report:\n\n"
        + json.dumps(workout_data, indent=2)
    )

    client = anthropic.Anthropic(api_key=api_key)

    def generate():
        try:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=1200,
                system=COACH_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps(text)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps('[ERROR] ' + str(e))}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    app.run(debug=True, port=5002)
