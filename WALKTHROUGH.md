# SenioCare - Walkthrough

## Architecture Overview

SenioCare uses a **Sequential Pipeline with Self-Correction Loop**:

```
User Input
    ↓
┌─────────────────┐
│  intent_agent   │ → Classifies intent (meal, medication, etc.)
└────────┬────────┘
         ↓
┌─────────────────┐
│  safety_agent   │ → Checks for emergencies/blocked content
└────────┬────────┘
         ↓
┌─────────────────┐
│ data_fetcher    │ → Retrieves user profile
└────────┬────────┘
         ↓
┌─────────────────────────────────┐
│       improvement_loop          │
│  ┌───────────────────────────┐  │
│  │    feature_agent          │  │ → Generates recommendation
│  └────────────┬──────────────┘  │
│               ↓                 │
│  ┌───────────────────────────┐  │
│  │    judge_agent            │  │ → Validates recommendation
│  └────────────┬──────────────┘  │
│               ↓                 │
│     Approved? ──No──→ Loop      │
│         ↓                       │
│        Yes                      │
└─────────┬───────────────────────┘
          ↓
┌─────────────────┐
│ formatter_agent │ → Formats in Egyptian Arabic
└────────┬────────┘
         ↓
    Final Response
```

## Key Components

| Agent | Role | Output Key |
|-------|------|------------|
| `intent_agent` | Classifies user request | `intent_result` |
| `safety_agent` | Safety check | `safety_status` |
| `data_fetcher_agent` | Gets user profile | `user_context` |
| `feature_agent` | Generates recommendation | `raw_recommendation` |
| `judge_agent` | Validates output | `judge_verdict` |
| `formatter_agent` | Localizes response | `final_response` |

## How to Run

```bash
cd "d:\PROJECTS\Graduation Project\SenioCare"
.venv\Scripts\activate
adk web --port 8000
```

## Sample Prompts
- "عايز أكل إيه للعشا؟ أنا عندي سكر"
- "إمتى موعد الدوا الجاي؟"
- "عايز تمارين خفيفة"
