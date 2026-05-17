# OTF Dashboard

A personal fitness dashboard that pulls your OrangeTheory Fitness beat report emails from Gmail, visualizes your workout history, and generates AI coaching insights powered by Claude.

![Dashboard preview](https://img.shields.io/badge/built%20with-Flask%20%2B%20Chart.js%20%2B%20Claude-orange)

## What it does

- **Pulls data automatically** from your OTF beat report emails via Gmail API
- **Visualizes trends** — calories, splat points, heart rate zones, workouts per week
- **Treadmill analytics** — distance, speed, incline, elevation over time
- **Rower analytics** — meters, wattage, 500m split, stroke rate over time
- **Personal records panel** — all-time bests for key metrics
- **Date range filtering** — Last 30d / 60d / 90d / All Time
- **AI coach panel** — Claude analyzes your full history and gives a personalized coaching report with actionable to-dos

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/otf-dashboard.git
cd otf-dashboard
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Get a Google Cloud credentials file

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Enable the **Gmail API** — search for it in the API library
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
5. Application type: **Desktop app**
6. Download the JSON file and save it as `credentials.json` in the project root
7. Go to **APIs & Services → OAuth consent screen**
   - Add your Gmail address as a test user

### 4. Set your Anthropic API key

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=your_key_here
OAUTHLIB_INSECURE_TRANSPORT=1
```

Get an API key at [console.anthropic.com](https://console.anthropic.com/).

### 5. Run

```bash
python3 app.py
```

Open [http://localhost:5002](http://localhost:5002) and click **Connect Gmail** to authorize.

## Data extracted per session

**Summary (from email snippet)**
`date · time · coach · location · zones 1–5 (minutes) · calories · splat points · avg HR · peak HR · steps`

**Treadmill** (from full email body)
`miles · time · avg/max speed · avg/max incline · avg/fastest pace · elevation`

**Rower** (from full email body)
`meters · time · avg/max wattage · avg/max speed · 500m split · stroke rate`

## Notes

- Your Gmail token is stored locally in `token.pickle` (gitignored — never committed)
- Your API key lives in `.env` (gitignored — never committed)
- `credentials.json` is also gitignored
- The app only requests `gmail.readonly` scope — it cannot send or modify email
- OTF emails come from `OTbeatReport@orangetheoryfitness.com`

## Tech stack

- **Backend:** Python / Flask
- **Gmail auth:** Google OAuth2 with PKCE
- **Email parsing:** BeautifulSoup4 + regex
- **Charts:** Chart.js 4.x
- **AI coach:** Anthropic Claude API (streamed via SSE)
