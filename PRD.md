# OTF Fitness Insights Dashboard — PRD
*Last revised: 2026-04-28 — updated to reflect shipped implementation*

---

## 1. Executive Summary

Ingrid built an AI-powered fitness coaching layer on top of an OrangeTheory Fitness (OTF) beat report dashboard for a regular OTF member. The dashboard pulls workout data directly from Gmail (via Google OAuth + Gmail API), parses both the summary stats and the full treadmill/rower performance data from each email body, visualizes trends across all sessions, and generates natural-language coaching insights and actionable to-dos via Claude — functioning like having a personal trainer review your workout history every week.

---

## 2. Problem Statement

### Who has this problem?
An active OTF member attending 2–4x per week who receives post-workout beat reports from OTbeatReport@orangetheoryfitness.com.

### What is the problem?
OTF emails contain rich per-session data (heart rate zones, calories, splat points, treadmill distance/speed/incline, rower wattage/split/stroke rate) but no interpretation — numbers without meaning across 26+ sessions.

### Why is it painful?
- No signal on whether performance is improving or declining
- No way to see treadmill or rower trends over time without a spreadsheet
- No guidance on what to focus on in the next workout
- No coach's eye on the data to spot patterns

### Evidence (from the data)
- 26+ sessions — enough history for meaningful trend analysis
- Splat points range 4–40, avg HR range 125–166 bpm — wide variance with no interpretation
- Coach rotation across multiple coaches — patterns by coach unanalyzed
- Treadmill data: 1.4–2.1 miles/session, elevation data, incline/pace per session
- Rower data: 400–600m/session, wattage and 500m split vary significantly

---

## 3. Target User & Persona

**Primary: The Committed Fitness Tracker**
- Attends OTF 2–4x per week consistently
- Motivated by data and measurable progress
- Wants to optimize performance but lacks a dedicated personal trainer
- Knows their numbers but doesn't know how to act on them

**Jobs to be done:**
- *"When I open the dashboard, I want to know if I'm on track or need to push harder"*
- *"I want to see how my treadmill and rower performance is trending"*
- *"I want someone to tell me what to focus on in my next workout"*

---

## 4. Strategic Context

**Why this matters:** OTF sells data-driven fitness but the beat reports are raw and passive. This dashboard turns passive reporting into an action-driving tool.

**Why now:** 26+ sessions of history already accumulated; infrastructure (Flask backend, Gmail OAuth, Chart.js) was already built before this initiative — the coaching and analytics layers are additive.

---

## 5. Solution Overview

### Data Pipeline
- Gmail OAuth2 authentication (one-time setup with Google Cloud credentials)
- Full email body fetched per message (HTML parsed via BeautifulSoup)
- Snippet regex extracts summary stats; HTML text extraction + regex extracts treadmill and rower sections
- Zero-width non-joiner characters (U+200C) that OTF embeds in time strings are stripped before parsing

**Fields extracted per session (28 total):**

*Summary:* date, time, coach, location, zone_gray/blue/green/orange/red (minutes), calories, splat_points, avg_hr, peak_hr, steps

*Treadmill:* treadmill_miles, treadmill_time, treadmill_avg_speed, treadmill_max_speed, treadmill_avg_incline, treadmill_max_incline, treadmill_avg_pace, treadmill_fastest_pace, treadmill_elevation

*Rower:* rower_meters, rower_time, rower_avg_wattage, rower_max_wattage, rower_avg_speed, rower_max_speed, rower_500m_split, rower_avg_stroke_rate

### Phase A — Enhanced Analytics

1. **Date range filter** — Last 30d / 60d / 90d / All Time; persists in localStorage; updates all charts and table

2. **Outlier exclusion** — hardcoded `EXCLUDED_DATES` array in JS filters specific sessions before any processing (e.g. sessions where the heart rate monitor had no battery); excluded from all charts, stats, PRs, and coach analysis

3. **Stats row** — 6 cards: Sessions (with workouts/week avg), Avg Calories (with trend ↑↓), Avg Splat Pts (with trend), Total TM Miles, Total Rower km, Avg Heart Rate (with trend)

4. **Personal Records panel** (always all-time, unaffected by date filter):
   - Best Calories, Best Splat Pts, Peak Heart Rate, Most Steps
   - Best TM Distance, Best TM Top Speed, Best Row Distance

5. **7 core charts** — Calories, Splat Points (goal 12+ highlighted), Avg/Peak HR, Steps, Heart Rate Zone Distribution (stacked bar), Avg Splat by Coach, Workouts per Week (with streak count)

6. **🏃 Treadmill Performance section:**
   - 4 charts: Distance (miles), Speed avg/max, Incline avg/max, Elevation
   - Summary stats panel: Total Miles, Avg Miles/Session, Avg Speed, Avg Incline, Total Elevation, Sessions with TM
   - Raw session table (collapsed by default, expandable)

7. **🚣 Rower Performance section:**
   - 4 charts: Distance (meters), Wattage avg/max, 500m Split (y-axis inverted — lower = faster), Stroke Rate
   - Summary stats panel: Total Distance, Avg Distance, Avg Wattage, Avg 500m Split, Avg Stroke Rate, Sessions with Rower
   - Raw session table (collapsed by default, expandable)

8. **Workout history table** — all sessions, newest first, includes all treadmill/rower fields with — for missing values

### AI Fitness Coach Panel ✅ Shipped

- **Endpoint:** `POST /api/coach-insights` — streams response via Server-Sent Events
- **Model:** claude-sonnet-4-6
- **Input:** Full structured workout history (all 28 fields for all sessions)
- **System prompt:** Frames Claude as an OTF coach with zone/splat context; requires 5 specific sections
- **Output streamed in 5 sections:**
  1. **Performance Summary** — recent overview with specific numbers
  2. **What's Working** — positive patterns by coach, time, zone strength
  3. **Areas to Watch** — dips with specific dates and values cited
  4. **To-Dos** — 3–5 numbered, actionable recommendations for next 1–2 weeks
  5. **Encouragement** — one motivating line citing a real achievement
- **UI:** Typewriter streaming with blinking cursor; cached per session; Regenerate button to re-call

---

## 6. Success Metrics

| Metric | Before | After (shipped) |
|---|---|---|
| Data fields surfaced | 14 (snippet only) | 28 (full email body) |
| Fields with trend interpretation | 0 | 3 (calories, splat, HR) |
| Personal records tracked | 0 | 7 |
| Dedicated equipment sections | 0 | 2 (treadmill, rower) |
| AI coaching insights | 0 | 5-section streamed report |
| Time-to-insight (open → understand next action) | N/A | < 30 sec via Coach panel |

---

## 7. User Stories & Requirements

### Epic Hypothesis
We believe that combining full-email data extraction, equipment-specific analytics, and an AI coaching layer will turn a passive data display into an active performance tool, making the member more intentional about each workout.

---

**Story 1: AI Coach Panel** ✅ Shipped
*As a member, I want a fitness coach to analyze my workout history and give me actionable to-dos.*

- [x] "Coach Insights" section below charts
- [x] Streams via SSE with 5 structured sections
- [x] Cached until Regenerate clicked
- [x] Loading spinner + error state

**Story 2: Personal Records Panel** ✅ Shipped
*As a member, I want to see my all-time personal bests.*

- [x] Best Calories, Best Splat Pts, Peak HR, Most Steps
- [x] Best TM Distance, Best TM Top Speed, Best Row Distance
- [x] Always computed from all-time data regardless of date filter

**Story 3: Date Range Filtering** ✅ Shipped
*As a member, I want to filter the dashboard by time window.*

- [x] Last 30d / 60d / 90d / All Time
- [x] All charts, stat cards (including Total TM Miles and Total Rower km), and table update; PRs always show all-time
- [x] Filter persists via localStorage

**Story 4: Trend Indicators** ✅ Shipped
*As a member, I want to see ↑↓ vs. prior period on key metrics.*

- [x] Avg Calories, Avg Splat, Avg HR show % change vs prior equal window
- [x] Green = improvement, red = decline

**Story 5: Coach Breakdown** ✅ Shipped
*As a member, I want to see my stats grouped by coach.*

- [x] Avg splat points by coach (bar chart, orange = above goal 12)

**Story 6: Workout Frequency** ✅ Shipped
*As a member, I want to see how many workouts I do per week.*

- [x] Workouts per week bar chart; orange = 3+ session weeks
- [x] Current streak displayed in section title

**Story 7: Treadmill Analytics** ✅ Shipped
*As a member, I want to see my treadmill performance trends over time.*

- [x] 4 charts: distance, speed, incline, elevation
- [x] Summary stats with totals and averages
- [x] Collapsible raw data table

**Story 8: Rower Analytics** ✅ Shipped
*As a member, I want to see my rower performance trends over time.*

- [x] 4 charts: distance, wattage, 500m split, stroke rate
- [x] Summary stats with totals and averages
- [x] Collapsible raw data table

**Story 9: Outlier Exclusion** ✅ Shipped
*As a member, I want to exclude sessions where my heart rate monitor had no battery so they don't skew my data.*

- [x] `EXCLUDED_DATES` array in JS filters specific sessions before any processing
- [x] Excluded sessions removed from all charts, stat cards, PRs, and coach analysis

---

## 8. Out of Scope

- **Mobile app** — web-only; responsive layout handles mobile
- **Nutrition tracking** — not in OTF emails
- **OTF official API integration** — email parsing is the data source
- **Social / sharing features**
- **Wearable device data** (Fitbit, Apple Watch)
- **Custom goal setting UI** — coach insights reference OTF's standard 12 splat goal
- **Push notifications or email digests**
- **Floor performance data** — OTF floor section not parsed (no structured metrics in email)

---

## 9. Dependencies & Risks

### Dependencies
- **Google Cloud project** with Gmail API enabled + OAuth 2.0 Desktop client credentials (`credentials.json`)
- **`ANTHROPIC_API_KEY`** env var for AI Coach panel
- **Python packages:** flask, google-auth, google-auth-oauthlib, google-api-python-client, anthropic, beautifulsoup4, lxml, python-dotenv

### Risks & Mitigations

| Risk | Mitigation |
|---|---|
| OTF email format change breaks parsing | Regex handles U+200C; per-field try/catch returns None gracefully |
| Full email fetch is slow (one API call per session) | Acceptable for personal use (~15–20s for 26 sessions); pagination handles large history |
| Claude generates generic advice | System prompt requires citing specific dates, coaches, and numbers |
| API cost for Claude calls | Cached per browser session; only regenerated on explicit click |
| Google token expiry | Token auto-refreshed via `google.auth.transport.requests.Request` |

---

## 10. Technical Architecture

### Files
| File | Purpose |
|---|---|
| `app.py` | Flask app — Gmail OAuth, email fetching, HTML parsing, `/api/workouts`, `/api/coach-insights` SSE |
| `templates/index.html` | Single-page dashboard — Chart.js, filter logic, AI coach streaming UI |
| `.env` | `ANTHROPIC_API_KEY` + `OAUTHLIB_INSECURE_TRANSPORT=1` (gitignored) |
| `credentials.json` | Google OAuth client secrets (user-provided, gitignored) |
| `token.pickle` | Cached OAuth token (gitignored) |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Excludes `.env`, `credentials.json`, `token.pickle` |

### Key endpoints
| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Serves dashboard HTML |
| `/login` | GET | Initiates Google OAuth with PKCE |
| `/oauth2callback` | GET | Handles OAuth redirect, stores token |
| `/api/workouts` | GET | Fetches + parses all OTF emails, returns JSON array |
| `/api/coach-insights` | POST | Streams Claude analysis via SSE |
| `/api/debug-email` | GET | Returns raw extracted text from latest email (debugging) |

---

## 11. Verification

1. `cd otf-dashboard && python3 app.py`
2. Open `http://localhost:5002` → should see "Connect Gmail" screen
3. Place `credentials.json` → Connect Gmail → sign in with your Gmail account
4. Verify 26+ workouts load with treadmill and rower data populated
5. Test date filter: "Last 30d" → should show only recent sessions
6. Verify PR panel shows all-time bests for calories, splat points, TM distance, row distance
7. Verify trend indicators reflect recent vs. prior period changes
8. Verify Coach Breakdown chart groups avg splat by coach
9. Verify Treadmill section: summary stats visible, raw table collapsed, expands on click
10. Verify Rower section: 500m split chart renders (y-axis inverted), summary avg split shown
11. Click "Get Coach Insights" with `ANTHROPIC_API_KEY` set → text streams with 5 sections
