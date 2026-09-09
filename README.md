# 🌫️ AirGuard AI – Daily Air Quality Action Agent

> A beginner-friendly, modular AI-powered air quality monitoring and health advisory system built with Python, Flask, and IBM watsonx.ai.

---

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Folder Structure](#folder-structure)
4. [Setup Instructions](#setup-instructions)
5. [Running the App](#running-the-app)
6. [API Keys & Configuration](#api-keys--configuration)
7. [Phase Breakdown](#phase-breakdown)
8. [IBM watsonx.ai Integration](#ibm-watsonxai-integration)
9. [Troubleshooting](#troubleshooting)

---

## Project Overview

AirGuard AI fetches **live AQI (Air Quality Index)** data for any city, runs it through an **AI agent pipeline**, and generates:

- 🌡️ Current AQI with PM2.5 / PM10 levels
- 🏥 Personalized health recommendations
- 📈 AQI forecast and early warnings
- 🤝 Community action suggestions
- 💬 AI chat assistant for air quality questions

---

## Architecture

```
Live AQI API (aqicn.org)
        ↓
   AQI Data Agent          ← interprets raw data
        ↓
  IBM watsonx.ai           ← generates health advice
        ↓
Health Advisory Agent      ← personalizes for user profile
        ↓
 Forecasting Agent         ← predicts next 24-hour AQI
        ↓
Community Action Agent     ← suggests local actions
        ↓
 AI Coordinator Agent      ← assembles Final Daily Plan
        ↓
   Flask Backend           ← REST API
        ↓
  Dashboard (HTML/JS)      ← Modern responsive UI
```

---

## Folder Structure

```
airguard/
├── app.py                      # Flask entry point
├── requirements.txt            # Python dependencies
├── .env.example                # Template for environment variables
├── .env                        # Your actual secrets (never commit!)
├── README.md
│
├── agents/                     # All AI agents live here
│   ├── __init__.py
│   ├── aqi_data_agent.py       # Phase 1 – Interprets AQI data
│   ├── health_advisory_agent.py# Phase 2 – Personalized health advice
│   ├── forecasting_agent.py    # Phase 2 – AQI prediction
│   ├── community_agent.py      # Phase 2 – Community actions
│   └── coordinator_agent.py    # Phase 3 – Orchestrates all agents
│
├── services/                   # External API wrappers
│   ├── __init__.py
│   ├── aqi_service.py          # AQICN API + fallback sample data
│   ├── ibm_watsonx_service.py  # IBM watsonx.ai API calls
│   └── langflow_service.py     # IBM Langflow pipeline calls
│
├── rag/                        # Phase 2 – RAG health guidelines
│   ├── __init__.py
│   ├── knowledge_base.py       # Health guidelines document store
│   └── health_guidelines.txt   # WHO / EPA AQI health guidelines
│
├── static/                     # Frontend assets
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── dashboard.js
│
└── templates/
    └── index.html              # Main dashboard page
```

---

## Setup Instructions

### 1. Clone / navigate to the project

```bash
cd airguard
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Now open .env and fill in your API keys
```

### 5. Get your API keys (see below)

---

## Running the App

```bash
python app.py
```

Then open your browser at **http://localhost:5000**

For production:

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

---

## API Keys & Configuration

### AQICN API Key (Free)
1. Go to https://aqicn.org/api/
2. Enter your email → receive a free token
3. Set `AQICN_API_KEY=your_token` in `.env`

> **No key?** The app automatically falls back to realistic sample data so you can still run and explore the dashboard.

### IBM watsonx.ai
1. Create a free IBM Cloud account at https://cloud.ibm.com
2. Provision a **watsonx.ai** instance
3. Go to **Manage → Access (IAM) → API Keys** → create a key
4. Find your **Project ID** in your watsonx.ai project settings
5. Set `IBM_API_KEY`, `IBM_PROJECT_ID`, `IBM_WATSONX_URL` in `.env`

> **No IBM key?** The app falls back to a rule-based health advice engine so the dashboard still works fully.

---

## Phase Breakdown

| Phase | Features | Status |
|-------|----------|--------|
| 1 | Live AQI fetch, AQI Data Agent, IBM AI health advice, Dashboard | ✅ Complete |
| 2 | Historical data, Forecasting Agent, RAG Health Advisory, Community Agent | ✅ Complete |
| 3 | Multi-Agent Coordinator, AI Chat Assistant, Final Daily Action Plan | ✅ Complete |

---

## IBM watsonx.ai Integration

The app calls IBM watsonx.ai's **text generation endpoint** with a structured prompt:

```
You are an air quality health advisor. Given the following AQI data:
- City: {city}
- AQI: {aqi} ({category})
- PM2.5: {pm25} µg/m³
- PM10: {pm10} µg/m³

Provide 3 personalized health recommendations...
```

The model (`ibm/granite-13b-chat-v2` by default) returns actionable advice which is parsed and displayed on the dashboard.

To swap models, change `IBM_MODEL_ID` in `.env` — no code changes needed.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` in your venv |
| AQI data not loading | Check `AQICN_API_KEY` or let it fall back to sample data |
| IBM AI not responding | Check `IBM_API_KEY` and `IBM_PROJECT_ID`; app uses rule-based fallback |
| Port 5000 in use | Change port: `python app.py --port 5001` |
| CORS error in browser | The app enables CORS by default for localhost |
