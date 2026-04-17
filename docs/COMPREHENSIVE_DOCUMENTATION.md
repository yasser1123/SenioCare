<![CDATA[# 🏥 SenioCare — Comprehensive Project Documentation

> **Version:** 2.0.0  
> **Author:** Ahmed Yasser  
> **License:** MIT  
> **Last Updated:** April 2026  
> **Repository:** [github.com/yasser1123/SenioCare](https://github.com/yasser1123/SenioCare)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Project Overview](#2-project-overview)
3. [Problem Statement & Motivation](#3-problem-statement--motivation)
4. [System Architecture](#4-system-architecture)
5. [Technology Stack](#5-technology-stack)
6. [Project Structure](#6-project-structure)
7. [Multi-Agent Pipeline — Detailed Design](#7-multi-agent-pipeline--detailed-design)
8. [Sub-Agent Specifications](#8-sub-agent-specifications)
9. [Tool Catalog](#9-tool-catalog)
10. [Database Design & Data Layer](#10-database-design--data-layer)
11. [Image Analysis Module](#11-image-analysis-module)
12. [API Server & Endpoints](#12-api-server--endpoints)
13. [Safety & Security Framework](#13-safety--security-framework)
14. [Session & Memory Management](#14-session--memory-management)
15. [Datasets & Data Pipeline](#15-datasets--data-pipeline)
16. [Unified Modelfile (Ollama)](#16-unified-modelfile-ollama)
17. [Testing Strategy](#17-testing-strategy)
18. [Deployment & Configuration](#18-deployment--configuration)
19. [Development Workflow & Git History](#19-development-workflow--git-history)
20. [Known Issues & Limitations](#20-known-issues--limitations)
21. [Future Work & Roadmap](#21-future-work--roadmap)
22. [Appendices](#22-appendices)

---

## 1. Executive Summary

**SenioCare** is an AI-powered, multi-agent healthcare assistant system designed as a **graduation project** to provide safe, personalized, and culturally adapted health support for elderly users in Egypt. The system leverages Google's **Agent Development Kit (ADK)** to orchestrate a 3-agent sequential pipeline that processes user requests through safety screening, intelligent tool calling, and warm Egyptian Arabic response formatting.

### Key Highlights

| Metric | Value |
|--------|-------|
| **Total Source Files** | ~25 Python modules |
| **Lines of Code** | ~4,500+ (Python) |
| **Database Tables** | 9 |
| **Agent Count** | 3 (Orchestrator → Feature → Formatter) |
| **Tools** | 12 callable tools |
| **API Endpoints** | 15 (ADK + Custom) |
| **Unit Tests** | 6 test modules |
| **Integration Tests** | 2 test modules |
| **Datasets** | 14 CSV files across 3 databases |
| **LLM Models** | 3 Ollama models |

---

## 2. Project Overview

### 2.1 What is SenioCare?

SenioCare is a specialized AI healthcare assistant for elderly Egyptian users. It bridges the gap between complex medical information and elderly end-users by:

1. **Understanding** user requests through intent classification
2. **Screening** for safety threats (emergencies, diagnosis requests)
3. **Personalizing** responses based on user health profiles (conditions, medications, allergies)
4. **Delivering** warm, culturally appropriate responses in Egyptian Arabic dialect

### 2.2 Core Capabilities

| Feature | Description |
|---------|-------------|
| 🍽️ **Meal Planning** | Condition-aware meal suggestions with recipes, nutrition data, drug-food interaction checks, and YouTube cooking videos |
| 💊 **Medication Management** | Schedule retrieval, next-dose reminders, intake logging, medication image OCR |
| 🏃 **Exercise Recommendations** | Mobility-adapted exercises with step-by-step guides, safety notes, and video tutorials |
| 🩺 **Symptom Assessment** | AI-powered symptom-to-disease matching with severity classification and precautions |
| ❓ **Medical Q&A** | Trusted medical information search from Mayo Clinic, WebMD, NIH, and WHO |
| 🚨 **Emergency Detection** | Real-time detection of emergency symptoms with immediate escalation guidance |
| 📸 **Medication Image OCR** | Extract medication names, active ingredients, and dosages from box photos |
| 📋 **Medical Report Analysis** | Two-pass AI analysis of lab reports with severity classification and historical tracking |
| 💬 **Emotional Support** | Warm conversational companionship for lonely or anxious elderly users |

---

## 3. Problem Statement & Motivation

### 3.1 The Challenge

Egypt has a growing elderly population with limited access to personalized healthcare guidance. Key challenges include:

- **Language Barrier**: Most health AI tools operate in English; elderly Egyptians prefer Egyptian Arabic dialect
- **Digital Literacy**: Complex health apps are difficult for elderly users to navigate
- **Personalization Gap**: Generic health advice doesn't account for individual medications, conditions, and allergies
- **Safety Concerns**: AI systems may provide dangerous advice (diagnoses, medication changes) without guardrails

### 3.2 SenioCare's Approach

SenioCare addresses these challenges through:

- **Egyptian Arabic localization** with culturally respectful honorifics (حضرتك, يا فندم)
- **Safety-first pipeline** that blocks diagnosis requests and detects emergencies
- **Personalized recommendations** using user health profiles stored in session state
- **Multi-agent architecture** ensuring each concern (safety, logic, presentation) is handled by a specialist

### 3.3 Target Users

- **Primary**: Elderly Egyptians (65+) with chronic conditions (diabetes, hypertension, arthritis)
- **Secondary**: Caregivers and family members of elderly patients
- **Tertiary**: Healthcare providers seeking patient engagement tools

---

## 4. System Architecture

### 4.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Mobile App / Frontend                   │
│                    (Flutter / React)                      │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP/REST
                         ▼
┌─────────────────────────────────────────────────────────┐
│                  Backend API Server                       │
│                (Kotlin Spring / Node.js)                  │
│  • User Registration   • Profile Management              │
│  • Firebase Auth       • Database (MongoDB/PostgreSQL)    │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP (POST /run_sse, /set-user-profile)
                         ▼
┌─────────────────────────────────────────────────────────┐
│              SenioCare AI Agent Server                    │
│                 (FastAPI + Google ADK)                    │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │            3-Agent Sequential Pipeline            │   │
│  │                                                    │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────┐  │   │
│  │  │ Orchestrator │→ │   Feature    │→ │Formatter│  │   │
│  │  │  (Safety +   │  │ (Tool Calls  │  │(Arabic  │  │   │
│  │  │  Intent +    │  │  + Decision  │  │Formatting│ │   │
│  │  │  Planning)   │  │  Making)     │  │  + UX)  │  │   │
│  │  └──────────────┘  └──────┬───────┘  └────────┘  │   │
│  │                           │                        │   │
│  │                    ┌──────┴──────┐                 │   │
│  │                    │   12 Tools   │                 │   │
│  │                    └─────────────┘                 │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐     │
│  │ SQLite DB│  │Sessions  │  │  Image Analysis   │     │
│  │(Health   │  │(aiosqlite│  │ (Ollama Vision)   │     │
│  │ Data)    │  │ persist) │  │                   │     │
│  └──────────┘  └──────────┘  └───────────────────┘     │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTP (localhost:11434)
                          ▼
              ┌───────────────────────┐
              │     Ollama Server     │
              │                       │
              │  • llama3.1:8b        │
              │  • olmocr2:7b-q8      │
              │  • llama3.2-vision    │
              └───────────────────────┘
```

### 4.2 Design Principles

1. **Sequential Pipeline**: Each agent has a single responsibility, reducing complexity and improving debuggability
2. **Tool Isolation**: Only the Feature Agent can call tools; Orchestrator reasons, Formatter presents
3. **State-Driven Personalization**: User health data is persisted via ADK's session state with `user:` prefix scoping
4. **Safety-First**: Emergency and blocked paths bypass tool-calling entirely for immediate response
5. **Self-Contained**: The system runs locally with Ollama — no cloud API keys required for core functionality

---

## 5. Technology Stack

### 5.1 Core Technologies

| Technology | Version | Purpose |
|-----------|---------|---------|
| **Python** | 3.10+ | Primary programming language |
| **Google ADK** | ≥ 0.1.0 | Agent orchestration framework |
| **FastAPI** | ≥ 0.109.0 | REST API server |
| **Uvicorn** | ≥ 0.27.0 | ASGI server |
| **SQLite** | Built-in | Local database for health data |
| **aiosqlite** | ≥ 0.19.0 | Async SQLite driver for session persistence |
| **Pydantic** | ≥ 2.0.0 | Data validation and serialization |
| **LiteLLM** | ≥ 1.0.0 | LLM provider abstraction (Ollama integration) |
| **google-genai** | ≥ 0.3.0 | Google GenAI SDK |
| **python-dotenv** | ≥ 1.0.0 | Environment variable management |
| **httpx** | ≥ 0.26.0 | Async HTTP client (image analysis) |

### 5.2 AI/ML Models (Ollama)

| Model | Size | Purpose | Temperature |
|-------|------|---------|-------------|
| `llama3.1:8b` | ~4.7 GB | All 3 agents (Orchestrator, Feature, Formatter) | 0.6 (Modelfile), 0.7 (default) |
| `richardyoung/olmocr2:7b-q8` | ~7.7 GB | Medication image OCR extraction | 0.1 |
| `llama3.2-vision` | ~7.9 GB | Medical report image analysis (two-pass) | 0.1 (extraction), 0.3 (evaluation) |

### 5.3 External Services

| Service | Purpose | Details |
|---------|---------|---------|
| **SerpAPI** | Web search, YouTube search, medical info search | Google search + YouTube engine via API |
| **Ollama** | Local LLM inference server | Runs on `localhost:11434` |
| **BeautifulSoup** | Web content extraction | Scrapes search result pages for medical info |

### 5.4 Development & Testing

| Tool | Purpose |
|------|---------|
| **pytest** | Test framework |
| **pytest-asyncio** | Async test support |
| **Git** | Version control |
| **ADK CLI** | Agent development & testing (`adk web`, `adk run`) |
| **Swagger UI** | Interactive API documentation (auto-generated at `/docs`) |

---

## 6. Project Structure

```
SenioCare/
├── .adk/                           # ADK configuration (auto-generated)
├── .git/                           # Git repository
├── .gitignore                      # Git ignore rules
├── .venv/                          # Python virtual environment
├── Datasets/                       # Training and reference datasets
│   ├── DDID Database/              # Drug-Disease Information Database
│   │   ├── disease_information_preprocessed.csv
│   │   ├── drug_foodherb_interaction_preprocessed.csv  (6.7 MB)
│   │   ├── drug_information_preprocessed.csv
│   │   ├── food_information_preprocessed.csv
│   │   └── herb_information_preprocessed.csv
│   ├── USDA Database/              # US Department of Agriculture Food Database
│   │   ├── food_nutrient_preprocessed.csv  (451 MB)
│   │   ├── food_portion_preprocessed.csv
│   │   ├── food_preprocessed.csv  (134 MB)
│   │   ├── measure_unit_preprocessed.csv
│   │   └── nutrient_preprocessed.csv
│   └── Various Datasets/
│       ├── Diseases Datasets/
│       │   ├── disease_precaution_preprocessed.csv
│       │   └── disease_symptoms_preprocessed.csv  (1 MB)
│       ├── Drug to Food interactions Datasets/
│       │   ├── drug_food_harmful_interactions_preprocessed.csv
│       │   └── drug_food_interactions_preprocessed.csv
│       └── Food Datasets/
│           ├── Egyptian Food_preprocessed.csv
│           └── personalized_diet_recommendations_preprocessed.csv
├── docs/                           # Documentation
│   ├── COMPREHENSIVE_DOCUMENTATION.md  ← (this file)
│   └── swagger-ui.html            # Static Swagger UI page
├── seniocare/                      # Main Python package
│   ├── .adk/                       # ADK agent configuration
│   ├── .env                        # Environment variables
│   ├── __init__.py                 # Package init (exports root_agent)
│   ├── agent.py                    # Root Agent — pipeline orchestration
│   ├── sub_agents/                 # Agent implementations
│   │   ├── __init__.py
│   │   ├── orchestrator_agent.py   # Agent 1: Safety + Intent + Planning
│   │   ├── feature_agent.py        # Agent 2: Tool Calling + Decisions
│   │   └── formatter_agent.py      # Agent 3: Egyptian Arabic Formatting
│   ├── tools/                      # Callable tools for Feature Agent
│   │   ├── __init__.py             # Tool exports
│   │   ├── nutrition.py            # get_meal_options, get_meal_recipe
│   │   ├── medication.py           # get_medication_schedule, log_medication_intake
│   │   ├── exercise.py             # get_exercises
│   │   ├── interactions.py         # check_drug_food_interaction
│   │   ├── symptoms.py             # assess_symptoms
│   │   ├── web_search.py           # search_web, search_youtube, search_medical_info
│   │   └── image_tools.py          # analyze_medication_image_tool, analyze_medical_report_tool
│   ├── data/                       # Data layer
│   │   ├── __init__.py
│   │   └── database.py             # SQLite schema + seed data (890 lines)
│   └── image_analysis/             # Image analysis engines
│       ├── __init__.py
│       ├── common.py               # Shared Ollama API utilities
│       ├── medication_analyzer.py  # Medication box OCR (olmocr2)
│       └── report_analyzer.py      # Medical report analysis (llama3.2-vision)
├── tests/                          # Test suite
│   ├── __init__.py
│   ├── conftest.py                 # Shared test fixtures
│   ├── test_database_tools.py      # Database tool tests
│   ├── unit/                       # Unit tests
│   │   ├── __init__.py
│   │   ├── test_exercise.py
│   │   ├── test_image_analysis.py
│   │   ├── test_interactions.py
│   │   ├── test_medication.py
│   │   ├── test_nutrition.py
│   │   └── test_symptoms.py
│   └── integration/                # Integration tests
│       ├── __init__.py
│       ├── test_api_endpoints.py
│       └── test_multi_tool_flows.py
├── main.py                         # FastAPI entry point (707 lines)
├── Modelfile                       # Ollama unified model configuration
├── requirements.txt                # Python dependencies
├── pytest.ini                      # Pytest configuration
├── LICENSE                         # MIT License
├── README.md                       # Project README
├── API_DOCS.md                     # API documentation
├── API_TESTING_RESULTS.md          # API test results
├── WALKTHROUGH.md                  # Architecture walkthrough
├── SenioCare_Plan.md               # Original architecture plan
├── sessions.db                     # ADK session database (SQLite)
├── test_api_endpoints.py           # Root-level API tests
├── test_search_standalone.py       # Search tool standalone tests
└── test_search_tools.py            # Search tool tests
```

---

## 7. Multi-Agent Pipeline — Detailed Design

### 7.1 Pipeline Flow

```
User Prompt + User Profile (from backend session state)
                    │
                    ▼
    ┌─────────────────────────────────┐
    │  before_agent_callback          │
    │  • populate_user_data()         │
    │  • Load user profile if missing │
    │  • Track conversation turns     │
    └───────────────┬─────────────────┘
                    │
                    ▼
    ┌─────────────────────────────────┐
    │  Agent 1: ORCHESTRATOR          │
    │  Model: ollama_chat/llama3.1:8b │
    │  Tools: NONE (reasoning only)   │
    │                                  │
    │  Step 1: Safety Check            │
    │    → EMERGENCY / BLOCKED /       │
    │      ALLOWED                     │
    │                                  │
    │  Step 2: Intent Classification   │
    │    → meal / medication /         │
    │      exercise / symptom /        │
    │      medical_qa / emotional /    │
    │      image_medication /          │
    │      image_report / emergency /  │
    │      blocked                     │
    │                                  │
    │  Step 3: Reasoning & Task Plan   │
    │    → Which tools to call, with   │
    │      what parameters, in order   │
    │                                  │
    │  Output Key: orchestrator_result │
    └───────────────┬─────────────────┘
                    │
    ┌───────────────┴───────────────────┐
    │           ALLOWED?                │
    ├── YES ────────────────────────────┤
    │                                   │
    │   ┌───────────────────────────┐   │
    │   │  Agent 2: FEATURE         │   │
    │   │  Model: llama3.1:8b       │   │
    │   │  Tools: 12 callable tools │   │
    │   │                           │   │
    │   │  1. Execute tool calls    │   │
    │   │  2. Analyze results       │   │
    │   │  3. Pick best option      │   │
    │   │  4. Check interactions    │   │
    │   │  5. Prepare presentation  │   │
    │   │                           │   │
    │   │  Output: feature_result   │   │
    │   └───────────┬───────────────┘   │
    │               │                   │
    ├── NO (BLOCKED/EMERGENCY) ─────────┤
    │   → Relay message directly        │
    └───────────────┬───────────────────┘
                    │
                    ▼
    ┌─────────────────────────────────┐
    │  Agent 3: FORMATTER             │
    │  Model: ollama_chat/llama3.1:8b │
    │  Tools: NONE                    │
    │                                  │
    │  • Transform data → Egyptian    │
    │    Arabic response              │
    │  • Apply structured templates   │
    │  • Add emoji section headers    │
    │  • Include safety reminders     │
    │  • Use respectful honorifics    │
    │                                  │
    │  Output Key: final_response     │
    └───────────────┬─────────────────┘
                    │
                    ▼
    ┌─────────────────────────────────┐
    │  after_agent_callback           │
    │  • auto_save_to_memory()        │
    │  • Save session to long-term    │
    │    memory for future recall     │
    └─────────────────────────────────┘
                    │
                    ▼
              Final Response
           (Egyptian Arabic)
```

### 7.2 State Management

ADK uses a scoped state system:

| Prefix | Scope | Lifetime | Example Keys |
|--------|-------|----------|--------------|
| `user:` | User-scoped | Across ALL sessions for same `user_id` | `user:chronicDiseases`, `user:medications`, `user:allergies` |
| (none) | Session-scoped | Single conversation thread | `conversation_turn_count`, `orchestrator_result` |
| `temp:` | Invocation-scoped | Single agent turn | `_meal_tool_called`, `_exercise_tool_called` |

### 7.3 Agent Output Keys

Each agent writes its output to a specific key in session state:

| Agent | Output Key | Consumed By |
|-------|-----------|-------------|
| Orchestrator | `orchestrator_result` | Feature Agent |
| Feature | `feature_result` | Formatter Agent |
| Formatter | `final_response` | User (final output) |

---

## 8. Sub-Agent Specifications

### 8.1 Orchestrator Agent (`orchestrator_agent.py`)

**Purpose**: First agent — evaluates safety, classifies intent, analyzes user profile, and creates a structured task plan.

| Property | Value |
|----------|-------|
| **Name** | `orchestrator_agent` |
| **Model** | `ollama_chat/llama3.1:8b` (via LiteLLM) |
| **Tools** | None (reasoning only) |
| **Output Key** | `orchestrator_result` |
| **Lines of Code** | 290 |
| **Instruction Size** | ~21 KB |

**Safety Classification Matrix:**

| Status | Trigger | Action |
|--------|---------|--------|
| `EMERGENCY` | Chest pain, stroke symptoms, loss of consciousness, severe bleeding, suicidal thoughts | Skip tools, write EMERGENCY_MESSAGE, direct to Formatter |
| `BLOCKED` | Diagnosis requests, medication prescriptions, dosage changes | Skip tools, write BLOCKED_MESSAGE, redirect to doctor |
| `ALLOWED` | All other safe requests | Proceed to intent classification and task planning |

**Intent Categories:**

| Intent | Description | Tool Chain |
|--------|-------------|------------|
| `meal` | Food/nutrition requests | `get_meal_options` → `check_drug_food_interaction` → `get_meal_recipe` → `search_youtube` |
| `medication` | Medicine schedules/reminders | `get_medication_schedule`, optionally `log_medication_intake` |
| `exercise` | Physical activity requests | `get_exercises` → `search_youtube` (mandatory) |
| `symptom_assessment` | User reports symptoms | `assess_symptoms` → optionally `search_medical_info` |
| `medical_qa` | Health questions | `search_medical_info` |
| `emotional` | Companionship/support | No tools — direct empathetic response |
| `routine` | Daily schedule planning | No tools — advice generation |
| `image_medication` | Medication box photo | `analyze_medication_image_tool` |
| `image_report` | Medical report photo | `analyze_medical_report_tool` |

### 8.2 Feature Agent (`feature_agent.py`)

**Purpose**: Second agent — executes tool calls, makes decisions (best meal, safest exercise), and prepares structured data for the Formatter.

| Property | Value |
|----------|-------|
| **Name** | `feature_agent` |
| **Model** | `ollama_chat/llama3.1:8b` (via LiteLLM) |
| **Tools** | 12 tools |
| **Output Key** | `feature_result` |
| **Lines of Code** | 328 |

**Key Decision-Making Workflows:**

1. **Meal Workflow (4 tools)**:
   - Get 3 meal options → Check ALL ingredients for drug interactions → Eliminate unsafe meals → Select best → Get full recipe → Find YouTube video

2. **Exercise Workflow (2 tools, YouTube mandatory)**:
   - Get safe exercises for mobility level → Search YouTube for tutorial videos

3. **Symptom Workflow (1-2 tools)**:
   - Assess symptoms against disease database → If urgent, search medical info

Each tool has a **single-call guard** (e.g., `_meal_tool_called`) to prevent the LLM from calling the same tool multiple times in one turn.

### 8.3 Formatter Agent (`formatter_agent.py`)

**Purpose**: Third and final agent — transforms structured data into warm, friendly Egyptian Arabic responses using emoji-enhanced templates.

| Property | Value |
|----------|-------|
| **Name** | `formatter_agent` |
| **Model** | `ollama_chat/llama3.1:8b` (via LiteLLM) |
| **Tools** | None |
| **Output Key** | `final_response` |
| **Lines of Code** | 240 |

**Response Templates:**

| Type | Emoji Header | Sections |
|------|-------------|----------|
| 🍽️ Meal Recommendation | `🍽️ الوجبة المقترحة` | Greeting → Meal name → Recipe steps → Nutrition table → Drug interactions → YouTube video → Safety reminder |
| 🏃 Exercise Plan | `🏃 التمرين المناسب` | Greeting → Exercise name → Duration → Steps → Benefits → Safety notes → YouTube video → Doctor reminder |
| 💊 Medication Info | `💊 جدول الأدوية` | Greeting → Med list with doses → Schedule times → Next dose → Instructions → Reminder |
| 🩺 Symptom Alert | `🩺 التقييم` | Greeting → Severity badge → Matched condition → Precautions → Doctor recommendation |
| ❓ Medical Q&A | `❓` | Greeting → Simple answer → Key points → Sources → AI disclaimer |
| 🚨 Emergency | `🚨 تنبيه طوارئ` | Urgent alert → Emergency number (123) → First-aid steps → Stay calm message |
| ❌ Blocked | Kind message → Reason → Doctor redirect → Offer alternatives |

**Egyptian Arabic Style Guide:**

| Element | Usage |
|---------|-------|
| `حضرتك` (hadretik) | Formal "you" — required in every response |
| `يا فندم` (ya fendim) | Respectful acknowledgment — used in openings |
| `إن شاء الله` | For future actions/plans |
| `الحمد لله` | When contextually appropriate |
| `ربنا يديم عليك الصحة` | Closing blessing |
| `لو محتاج حاجة تانية، أنا موجود!` | Standard closing offer |

---

## 9. Tool Catalog

### 9.1 Overview

All tools are registered on the Feature Agent. Each tool receives a `ToolContext` parameter that provides access to session state (user profile data). All tools have **idempotency guards** to prevent repeated calls within a single turn.

### 9.2 Nutrition Tools (`nutrition.py`)

#### `get_meal_options(meal_type, tool_context)`

| Property | Detail |
|----------|--------|
| **Purpose** | Return condition-aware, allergy-safe meal suggestions |
| **Input** | `meal_type`: "breakfast" / "lunch" / "dinner" / "snack" |
| **Auto-Reads** | `user:chronicDiseases`, `user:allergies` from state |
| **Output** | Up to 3 meals with nutrition data, ingredients, prep time |
| **Algorithm** | 1) Query all meals by type → 2) Apply condition dietary rules (max nutrient thresholds) → 3) Exclude allergen-containing meals → 4) Return top 3 |

#### `get_meal_recipe(meal_id, tool_context)`

| Property | Detail |
|----------|--------|
| **Purpose** | Return full recipe for a selected meal |
| **Input** | `meal_id`: e.g., "M005" |
| **Output** | Recipe steps, tips, full nutrition breakdown, ingredients |

### 9.3 Medication Tools (`medication.py`)

#### `get_medication_schedule(tool_context)`

| Property | Detail |
|----------|--------|
| **Purpose** | Return user's medication schedule with next doses |
| **Auto-Reads** | `user:user_id` from state |
| **Output** | All medications with dose, schedule times, purpose, instructions, and computed next doses |

#### `log_medication_intake(medication_name, tool_context)`

| Property | Detail |
|----------|--------|
| **Purpose** | Log that the user took their medication |
| **Input** | `medication_name`: e.g., "Metformin" |
| **Output** | Confirmation with timestamp |

### 9.4 Exercise Tool (`exercise.py`)

#### `get_exercises(tool_context)`

| Property | Detail |
|----------|--------|
| **Purpose** | Return safe exercises for the user's mobility level |
| **Auto-Reads** | `user:mobilityStatus`, `user:chronicDiseases` from state |
| **Output** | Up to 2 exercises with Arabic names, steps, benefits, safety notes |
| **Algorithm** | Query exercises by mobility level → Exclude exercises with `avoid_conditions` matching user's conditions |

### 9.5 Drug-Food Interaction Tool (`interactions.py`)

#### `check_drug_food_interaction(food_names, tool_context)`

| Property | Detail |
|----------|--------|
| **Purpose** | Check if user's medications interact with given foods |
| **Input** | `food_names`: list of food strings |
| **Auto-Reads** | `user:medications` from state |
| **Output** | Harmful, positive, and neutral interactions with severity, advice, and a dangerous-flag |

### 9.6 Symptom Assessment Tool (`symptoms.py`)

#### `assess_symptoms(symptoms, tool_context)`

| Property | Detail |
|----------|--------|
| **Purpose** | Match symptoms to diseases with severity classification |
| **Input** | `symptoms`: list of symptom strings |
| **Auto-Reads** | `user:chronicDiseases` from state (for confidence boosting) |
| **Output** | Top 3 matched diseases with confidence %, severity (EMERGENCY/URGENT/MONITOR/NORMAL), precautions |
| **Algorithm** | Fuzzy symptom matching → Base confidence calculation → 15% boost for condition-related diseases → Sort by severity then confidence |

### 9.7 Web Search Tools (`web_search.py`)

#### `search_web(query, tool_context, num_results, extract_content, language)`

| Property | Detail |
|----------|--------|
| **Engine** | SerpAPI → Google |
| **Content Extraction** | BeautifulSoup scraping of result pages |
| **Default Language** | Arabic (`ar`) with Egypt region (`eg`) |

#### `search_youtube(query, tool_context, num_results, video_duration, sort_by)`

| Property | Detail |
|----------|--------|
| **Engine** | SerpAPI → YouTube |
| **Features** | Duration filtering (short/medium/long), embed URL generation |
| **Default** | Arabic interface, Egypt region |

#### `search_medical_info(query, tool_context, prefer_trusted_sources)`

| Property | Detail |
|----------|--------|
| **Engine** | SerpAPI → Google with site restrictions |
| **Trusted Sources** | mayoclinic.org, webmd.com, healthline.com, nih.gov, who.int, cdc.gov, medlineplus.gov, clevelandclinic.org |
| **Fallback** | Local knowledge base with curated diabetes, hypertension, arthritis information |

### 9.8 Image Analysis Tools (`image_tools.py`)

#### `analyze_medication_image_tool(image_base64, tool_context)`

| Property | Detail |
|----------|--------|
| **Purpose** | OCR extraction from medication box photos |
| **Delegates To** | `medication_analyzer.py` → Ollama `olmocr2:7b-q8` |
| **Storage** | None — returns data directly |

#### `analyze_medical_report_tool(image_base64, tool_context)`

| Property | Detail |
|----------|--------|
| **Purpose** | AI analysis of medical reports (blood tests, X-rays, etc.) |
| **Delegates To** | `report_analyzer.py` → Ollama `llama3.2-vision` |
| **Storage** | Results stored in `medical_reports` database table |

---

## 10. Database Design & Data Layer

### 10.1 Overview

SenioCare uses two separate SQLite databases:

| Database | File | Purpose |
|----------|------|---------|
| **Health Data** | `seniocare/data/seniocare_test.db` | Meals, medications, exercises, disease symptoms, drug interactions, medical reports |
| **Session Data** | `sessions.db` | ADK session persistence (managed by `DatabaseSessionService`) |

### 10.2 Schema — Health Data Database

#### `meals` Table

| Column | Type | Description |
|--------|------|-------------|
| `meal_id` | TEXT PK | Unique ID (e.g., "M001") |
| `name_ar` | TEXT | Arabic name (e.g., "فول مدمس بزيت الزيتون") |
| `name_en` | TEXT | English name |
| `meal_type` | TEXT | "breakfast" / "lunch" / "dinner" / "snack" |
| `category` | TEXT | "legumes" / "protein" / "grains" / "dairy" / etc. |
| `ingredients` | TEXT (JSON) | Array of ingredient names |
| `energy_kcal` | REAL | Calories |
| `protein_g` | REAL | Protein in grams |
| `fat_g` | REAL | Fat in grams |
| `carbohydrate_g` | REAL | Carbs in grams |
| `fiber_g` | REAL | Fiber in grams |
| `sodium_mg` | REAL | Sodium in milligrams |
| `sugar_g` | REAL | Sugar in grams |
| `prep_time` | TEXT | Preparation time |
| `notes_ar` | TEXT | Arabic notes |
| `recipe_steps` | TEXT (JSON) | Array of recipe steps in Arabic |
| `recipe_tips` | TEXT | Tips in Arabic |

**Sample Data**: 19 meals (4 breakfast, 6 lunch, 5 dinner, 4 snack) — includes traditional Egyptian dishes (Foul Medames, Koshari, Molokhia, Lentil Soup).

#### `condition_dietary_rules` Table

| Column | Type | Description |
|--------|------|-------------|
| `rule_id` | TEXT PK | Unique ID |
| `condition` | TEXT UNIQUE | Health condition (diabetes, hypertension, etc.) |
| `avoid_high` | TEXT (JSON) | Nutrients to limit |
| `prefer_high` | TEXT (JSON) | Nutrients to prefer |
| `avoid_foods` | TEXT (JSON) | Foods to avoid |
| `max_values` | TEXT (JSON) | Maximum nutrient thresholds |

**Sample Rules:**

| Condition | Max Sugar | Max Sodium | Max Fat | Max Carbs |
|-----------|----------|-----------|---------|----------|
| Diabetes | 10g | — | — | 45g |
| Hypertension | — | 200mg | — | — |
| Arthritis | — | — | 20g | — |
| Heart Disease | 12g | 150mg | 15g | — |
| Kidney Disease | — | 100mg | — | — |

#### `drug_food_interactions` Table (20 records)

| Column | Type | Description |
|--------|------|-------------|
| `interaction_id` | TEXT PK | Unique ID |
| `drug_name` | TEXT | Drug name (e.g., "metformin") |
| `food_name` | TEXT | Food name (e.g., "grapefruit") |
| `effect` | TEXT | "negative" / "positive" / "no_effect" |
| `severity` | TEXT | "mild" / "moderate" / "severe" |
| `conclusion` | TEXT | Scientific explanation |
| `advice` | TEXT | Patient-facing advice |

#### `disease_symptoms` Table (15 records)

| Column | Type | Description |
|--------|------|-------------|
| `disease_id` | TEXT PK | Unique ID (e.g., "DIS001") |
| `disease_name` | TEXT | Disease name |
| `symptoms` | TEXT (JSON) | Array of symptom strings |
| `severity` | TEXT | "EMERGENCY" / "URGENT" / "MONITOR" / "NORMAL" |
| `description` | TEXT | Disease description |

**Severity Distribution**: 3 EMERGENCY, 4 URGENT, 4 MONITOR, 4 NORMAL diseases.

#### `disease_precautions` Table

Linked to `disease_symptoms` via `disease_id`. Contains 2-4 precautionary measures per disease.

#### `food_allergens` Table

Maps food items to allergen categories (shellfish, dairy, gluten, nuts, eggs, fish, soy).

#### `medications` Table

Sample medication schedules for test users (user_001 through user_004).

#### `exercises` Table

Exercise recommendations by mobility level (limited, moderate, active). Each exercise includes Arabic/English names, step-by-step instructions, benefits, safety notes, and conditions to avoid.

#### `medical_reports` Table

Stores AI-analyzed medical report results with report ID, lab values, health summary, severity level, and timestamp.

### 10.3 Database Indexes

```sql
idx_meals_type                ON meals(meal_type)
idx_drug_interactions_drug    ON drug_food_interactions(drug_name)
idx_drug_interactions_food    ON drug_food_interactions(food_name)
idx_allergens_allergen        ON food_allergens(allergen)
idx_medications_user          ON medications(user_id)
idx_exercises_mobility        ON exercises(mobility_level)
idx_precautions_disease       ON disease_precautions(disease_id)
idx_medical_reports_user      ON medical_reports(user_id)
```

### 10.4 Database Initialization

The database auto-initializes on first access via `get_connection()`. The `reset_database()` function (called from `agent.py` on startup) ensures clean test data is available. WAL journal mode is enabled for concurrent read performance.

---

## 11. Image Analysis Module

### 11.1 Architecture

```
┌────────────────────────────────────────┐
│            image_analysis/             │
│                                        │
│  common.py ─────────────────────────── │ Shared utilities
│  • check_model_available()             │ • Ollama API health check
│  • call_ollama_vision()                │ • Send image + prompt to Ollama
│  • parse_json_from_response()          │ • Extract JSON from model output
│  • validate_base64_image()             │ • Validate image data
│  • strip_base64_prefix()               │ • Clean data URLs
│                                        │
│  medication_analyzer.py ───────────── │
│  • Model: richardyoung/olmocr2:7b-q8  │
│  • Single-pass OCR extraction         │
│  • Returns: name, ingredient, dosage  │
│  • No database storage                │
│                                        │
│  report_analyzer.py ──────────────── │
│  • Model: llama3.2-vision             │
│  • Two-pass analysis:                 │
│    1. Extract structured data         │
│    2. Evaluate health situation       │
│  • Severity: NORMAL/ATTENTION/        │
│              CRITICAL                  │
│  • Rule-based fallback severity       │
│  • Stores results in database         │
└────────────────────────────────────────┘
```

### 11.2 Medication Image Analysis

**Model**: `richardyoung/olmocr2:7b-q8` (OCR-specialized model)

**Process**:
1. Validate base64 image → Check model availability → Clean base64
2. Send image with structured OCR prompt to Ollama
3. Parse JSON response → Extract medication name, active ingredient, dosage, manufacturer, expiry date
4. Return `MedicationScanResult` (Pydantic model)

**No database storage** — data returned directly to the backend for the user to add to their profile.

### 11.3 Medical Report Analysis

**Model**: `llama3.2-vision` (multimodal vision model)

**Two-Pass Process**:

| Pass | Purpose | Temperature | Prompt |
|------|---------|-------------|--------|
| **Pass 1** | Extract structured lab values, findings, report type | 0.1 | Focuses on precision — reads all visible test values, flags abnormals |
| **Pass 2** | Generate health evaluation, severity, recommendations | 0.3 | Slightly creative — produces human-readable health summary |

**Severity Classification (Dual System)**:

1. **AI-based**: Model returns `NORMAL` / `ATTENTION` / `CRITICAL`
2. **Rule-based fallback**: Thresholds for common lab values (glucose, HbA1c, blood pressure, creatinine, potassium, hemoglobin, etc.)
3. **Final**: Uses the MORE severe of the two assessments (safety-first principle)

**Critical Lab Value Thresholds (Rule-Based):**

| Test | Critical High | Critical Low |
|------|--------------|-------------|
| Glucose | ≥ 300 mg/dL | ≤ 50 mg/dL |
| HbA1c | ≥ 10.0% | — |
| Systolic BP | ≥ 180 mmHg | — |
| Creatinine | ≥ 4.0 mg/dL | — |
| Potassium | ≥ 6.0 mEq/L | ≤ 3.0 mEq/L |
| Hemoglobin | — | ≤ 7.0 g/dL |

**Safety Disclaimers** (auto-appended to every report):
- ⚕️ AI-generated analysis, NOT a medical diagnosis
- 👨‍⚕️ Always consult your doctor
- 📋 Take report to next appointment
- ⚠️ Seek immediate attention for severe symptoms

---

## 12. API Server & Endpoints

### 12.1 Server Configuration

| Setting | Value |
|---------|-------|
| **Framework** | FastAPI (powered by Google ADK's `get_fast_api_app`) |
| **Port** | 8080 (configurable via `--port` or `PORT` env) |
| **ASGI Server** | Uvicorn |
| **Session Storage** | SQLite + aiosqlite (`sessions.db`) |
| **Memory Service** | InMemoryMemoryService (default) |
| **CORS** | Open (`*`) for development |
| **Web UI** | Enabled at root URL (ADK web interface) |

### 12.2 Custom OpenAPI Schema

The standard FastAPI OpenAPI generation crashes due to ADK internal types (MCP/proto-plus Pydantic schemas). SenioCare implements a **custom `openapi()` method** that:

1. Generates schema only for custom endpoints (safe routes)
2. Manually documents ADK endpoints (`/run_sse`, session management)
3. Tags endpoints into 5 categories: Health, User Profile, Image Analysis, Agent, Sessions

### 12.3 Endpoint Reference

#### Health Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health check |
| `GET` | `/api-docs` | Redirect to Swagger UI |
| `GET` | `/export-openapi` | Download OpenAPI spec as JSON |

#### User Profile Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/set-user-profile/{user_id}` | Push full health profile |
| `GET` | `/get-user-profile/{user_id}` | Retrieve stored profile |
| `POST` | `/sync-user-profile/{user_id}` | Partial profile update |

**Profile Data Model (`UserProfileRequest`):**

```json
{
    "user_name": "Ahmed",
    "age": 72,
    "weight": 78.0,
    "height": 170.0,
    "gender": "male",
    "chronicDiseases": ["diabetes", "hypertension"],
    "allergies": ["shellfish"],
    "medications": [
        {"name": "Metformin", "dose": "500mg"},
        {"name": "Lisinopril", "dose": "10mg"}
    ],
    "mobilityStatus": "limited",
    "bloodType": "A+",
    "caregiver_ids": []
}
```

#### Image Analysis Endpoints

| Method | Path | Description | Model Required |
|--------|------|-------------|----------------|
| `POST` | `/analyze-medication-image` | Medication box OCR | `olmocr2:7b-q8` |
| `POST` | `/analyze-medical-report` | Medical report analysis | `llama3.2-vision` |
| `GET` | `/user-medical-reports/{user_id}` | Report history | None |

#### Agent Endpoints (ADK-powered)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/list-apps` | List available agents |
| `POST` | `/run_sse` | Send message to agent |
| `POST` | `/apps/{app}/users/{user}/sessions/{session}` | Create session |
| `GET` | `/apps/{app}/users/{user}/sessions/{session}` | Get session info |
| `GET` | `/apps/{app}/users/{user}/sessions` | List user sessions |
| `DELETE` | `/apps/{app}/users/{user}/sessions/{session}` | Delete session |

### 12.4 Integration Flow

```
Backend (after user registration):
  1. POST /set-user-profile/user_123  → Push health profile
  2. POST /apps/seniocare/users/user_123/sessions/sess_1  → Create session
  3. POST /run_sse  → Send user message
  4. (Response contains final agent response in Egyptian Arabic)
```

---

## 13. Safety & Security Framework

### 13.1 Multi-Layered Safety

```
Layer 1: INTENT CLASSIFICATION
  └── Detects emergency keywords before any processing

Layer 2: SAFETY CHECK (Orchestrator Agent)
  └── EMERGENCY → Immediate escalation, no tools called
  └── BLOCKED → Kind refusal, redirect to doctor
  └── ALLOWED → Proceed to tool calling

Layer 3: TOOL-LEVEL SAFETY
  └── Nutrition: Condition-aware filtering, allergen exclusion
  └── Interactions: Drug-food interaction checking
  └── Symptoms: Severity classification with emergency detection
  └── Exercises: Condition-based exercise exclusion

Layer 4: RESPONSE SAFETY (Formatter)
  └── Always includes doctor consultation reminders
  └── Never presents AI advice as medical diagnosis
  └── Safety disclaimers on every medical response
```

### 13.2 Emergency Protocol

When the system detects an emergency:

1. **Orchestrator** immediately sets `safety_status = EMERGENCY`
2. **Feature Agent** skips ALL tool calls — relays emergency message
3. **Formatter** generates urgent response with:
   - 🚨 Alert emoji and banner
   - Emergency number (123 in Egypt)
   - First-aid instructions
   - Stay calm messaging
   - Caring closing

### 13.3 No-Diagnosis Policy

The system enforces strict rules across all agents:

- ❌ **Never** diagnose medical conditions
- ❌ **Never** prescribe medications
- ❌ **Never** suggest dosage changes
- ❌ **Never** recommend stopping medications
- ✅ **Always** include "استشير الدكتور" (consult doctor)
- ✅ **Always** mark information as "for educational purposes only"

---

## 14. Session & Memory Management

### 14.1 Session Service

| Component | Implementation |
|-----------|---------------|
| **SessionService** | `DatabaseSessionService` with SQLite (`sessions.db`) |
| **Driver** | `aiosqlite` (async-compatible) |
| **Persistence** | Sessions survive server restarts |
| **Management** | Create/Get/List/Delete via ADK REST endpoints |

### 14.2 Memory Service

| Component | Implementation |
|-----------|---------------|
| **MemoryService** | `InMemoryMemoryService` (default) |
| **Persistence** | Lost on server restart |
| **Auto-Save** | `after_agent_callback` saves session to memory after each turn |
| **Future** | Planned migration to Vertex AI Memory Bank for production |

### 14.3 User Profile Persistence

- Backend calls `POST /set-user-profile/{user_id}` once after registration
- Profile data is stored with `user:` prefix in session state
- ADK automatically loads `user:`-prefixed keys for the same `user_id` across sessions
- No need to re-send profile data in subsequent sessions

### 14.4 Test Mode

When running with `adk web` (no backend), a `TEST_USER_PROFILE` is auto-populated:

```python
{
    "user:user_id": "user_001",
    "user:user_name": "Ahmed",
    "user:age": 72,
    "user:chronicDiseases": ["diabetes", "hypertension"],
    "user:medications": [
        {"name": "Metformin", "dose": "500mg"},
        {"name": "Lisinopril", "dose": "10mg"}
    ],
    "user:mobilityStatus": "limited",
    ...
}
```

---

## 15. Datasets & Data Pipeline

### 15.1 Dataset Inventory

SenioCare uses **14 preprocessed CSV datasets** across 3 database categories totaling **~1.24 GB**:

#### DDID (Drug-Disease Information Database)

| File | Size | Content |
|------|------|---------|
| `disease_information_preprocessed.csv` | 78 KB | Disease descriptions and metadata |
| `drug_foodherb_interaction_preprocessed.csv` | 6.7 MB | Drug-food-herb interaction records |
| `drug_information_preprocessed.csv` | 1.1 MB | Drug profiles and properties |
| `food_information_preprocessed.csv` | 112 KB | Food nutritional profiles |
| `herb_information_preprocessed.csv` | 280 KB | Herbal supplement data |

#### USDA (U.S. Department of Agriculture)

| File | Size | Content |
|------|------|---------|
| `food_nutrient_preprocessed.csv` | **451 MB** | Detailed nutrient data per food item |
| `food_preprocessed.csv` | **134 MB** | Food item catalog |
| `food_portion_preprocessed.csv` | 2.2 MB | Serving sizes and portions |
| `measure_unit_preprocessed.csv` | 1.4 KB | Unit definitions |
| `nutrient_preprocessed.csv` | 10 KB | Nutrient metadata |

#### Various Domain-Specific Datasets

| File | Size | Content |
|------|------|---------|
| `disease_symptoms_preprocessed.csv` | 1 MB | Disease-to-symptom mappings |
| `disease_precaution_preprocessed.csv` | 3.5 KB | Precautionary measures |
| `drug_food_harmful_interactions_preprocessed.csv` | 26 KB | Harmful drug-food interactions |
| `drug_food_interactions_preprocessed.csv` | 30 KB | All drug-food interactions |
| `Egyptian Food_preprocessed.csv` | 50 KB | Traditional Egyptian food data |
| `personalized_diet_recommendations_preprocessed.csv` | 796 KB | Diet recommendations |

### 15.2 Data Pipeline Approach

The current implementation uses a **curated seed approach**:

1. **Raw datasets** are stored in `Datasets/` for reference and future RAG integration
2. **Curated test data** is hardcoded in `database.py` (890 lines) with representative samples derived from the raw datasets
3. **Database initialization** happens on first access — the `_initialize_database()` function creates tables and inserts seed data

### 15.3 Future Data Plans

- Migrate from curated seed data to **full dataset indexing**
- Implement **vector embeddings** (FAISS/Milvus) for RAG-powered medical Q&A
- Build an **ETL pipeline** to import USDA nutritional data into the meals table
- Integrate DDID drug interaction data for comprehensive coverage

---

## 16. Unified Modelfile (Ollama)

### 16.1 Purpose

The `Modelfile` creates a **single unified model** (`llama3.1:8b`) that handles ALL pipeline stages — used for **benchmarking** against the multi-agent approach.

### 16.2 Configuration

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `temperature` | 0.6 | Lower for consistent medical advice |
| `top_p` | 0.9 | Balanced coherent + varied |
| `top_k` | 40 | Moderate vocabulary selection |
| `repeat_penalty` | 1.1 | Allow natural repetition |
| `repeat_last_n` | 512 | Large anti-repetition window |
| `num_ctx` | 16384 | Large context for profile + history |
| `num_predict` | -1 | No token limit |
| `mirostat` | 2 | Consistent output quality |

### 16.3 System Prompt Sections

1. **Identity & Core Values**: Warm Egyptian companion persona
2. **Intent Classification**: 7 intent categories
3. **Safety Screening**: Emergency triggers, blocked request types
4. **User Profiles**: Mock data for testing (Ahmed, Fatma)
5. **Available Knowledge**: Embedded meal, exercise, medication, and medical data
6. **Response Generation**: Structure and style rules
7. **Egyptian Arabic Style**: Honorifics, warm phrases, emoji usage
8. **Strict Rules**: Always/Never lists
9. **Example Interactions**: 3 complete example dialogues

### 16.4 Build & Run

```bash
# Build the unified model
ollama create seniocare -f Modelfile

# Run it
ollama run seniocare
```

---

## 17. Testing Strategy

### 17.1 Test Configuration

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
timeout = 30
markers =
    unit: Unit tests (isolated, no external deps)
    integration: Integration tests (need DB or API)
    slow: Slow tests (LLM calls, web search)
```

### 17.2 Unit Tests (`tests/unit/`)

| Test Module | Tests | Coverage |
|-------------|-------|----------|
| `test_nutrition.py` | 11 KB | `get_meal_options`, `get_meal_recipe`, condition filtering, allergen exclusion |
| `test_medication.py` | 6.2 KB | `get_medication_schedule`, `log_medication_intake`, edge cases |
| `test_exercise.py` | 5.6 KB | `get_exercises`, mobility filtering, condition exclusion |
| `test_interactions.py` | 6.5 KB | `check_drug_food_interaction`, severity detection, multi-drug checks |
| `test_symptoms.py` | 11.7 KB | `assess_symptoms`, fuzzy matching, severity classification, confidence boosting |
| `test_image_analysis.py` | 15.7 KB | Medication OCR, report analysis, base64 validation, JSON parsing |

### 17.3 Integration Tests (`tests/integration/`)

| Test Module | Tests | Coverage |
|-------------|-------|----------|
| `test_api_endpoints.py` | 7.9 KB | FastAPI endpoint testing, profile CRUD, session management |
| `test_multi_tool_flows.py` | 5.8 KB | Multi-tool workflow testing (meal + interaction + recipe chains) |

### 17.4 Standalone Tests (Root Level)

| Test File | Coverage |
|-----------|----------|
| `test_api_endpoints.py` | Quick API endpoint verification |
| `test_search_standalone.py` | SerpAPI search tool testing |
| `test_search_tools.py` | Web/YouTube/medical search integration |
| `test_database_tools.py` | Database tool comprehensive testing |

### 17.5 Test Fixtures (`conftest.py`)

- Mock `ToolContext` with configurable session state
- Test user profiles with various condition combinations
- Database seeding and cleanup
- Async test support

### 17.6 Running Tests

```bash
# Activate virtual environment
.venv\Scripts\activate

# Run all tests
pytest

# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/unit/test_nutrition.py
```

---

## 18. Deployment & Configuration

### 18.1 Prerequisites

- Python 3.10+
- Ollama installed and running on `localhost:11434`
- Required models pulled:
  ```bash
  ollama pull llama3.1:8b
  ollama pull richardyoung/olmocr2:7b-q8  # For medication OCR
  ollama pull llama3.2-vision              # For report analysis
  ```

### 18.2 Installation

```bash
# Clone repository
git clone https://github.com/yasser1123/SenioCare.git
cd SenioCare

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 18.3 Environment Variables

File: `seniocare/.env`

```env
GOOGLE_GENAI_USE_VERTEXAI=0
# GOOGLE_API_KEY= (optional — for Gemini instead of Ollama)
OLLAMA_API_BASE="http://localhost:11434"
```

### 18.4 Running the Server

```bash
# Option 1: API Server (production-like)
python main.py                    # Port 8080
python main.py --port 3000        # Custom port

# Option 2: ADK Web UI (development/testing)
adk web seniocare.agent:root_agent
adk web --port 8000

# Option 3: ADK CLI (interactive)
adk run seniocare.agent:root_agent
```

### 18.5 CORS Configuration

For development, all origins are allowed (`*`). For production, update `ALLOWED_ORIGINS` in `main.py`:

```python
ALLOWED_ORIGINS = [
    "https://your-backend-domain.com",
    "https://your-app-domain.com",
]
```

### 18.6 Switching to Google Gemini

To use Gemini instead of Ollama:

1. Set `GOOGLE_API_KEY` in `.env`
2. Comment out `OLLAMA_API_BASE`
3. Change model references in sub-agents from `ollama_chat/llama3.1:8b` to appropriate Gemini model

---

## 19. Development Workflow & Git History

### 19.1 Git Commit History

| # | Commit | Description |
|---|--------|-------------|
| 1 | `ed6a1bf` | Initial commit of SenioCare: Elderly Healthcare Assistant |
| 2 | `48aa24c` | Initial commit |
| 3 | `94ed362` | Merge remote changes (LICENSE) |
| 4 | `2acbe2e` | feat: add API server with FastAPI integration for backend connectivity |
| 5 | `7d53a72` | fix: suppress Pydantic warnings and add health check endpoint |
| 6 | `3f2faac` | fix: add custom OpenAPI schema to resolve /docs Pydantic errors |
| 7 | `027b5b5` | feat: add image analysis endpoint for medication and medical report processing |
| 8 | `9dcc659` | refactor: split image analysis into two separate models + 3-agent pipeline |
| 9 | `1aef5ce` | fix: google-genai dependency name |
| 10 | `71672e3` | Fix Vercel deployment: package names, routing, sqlite path |

### 19.2 Development Phases

| Phase | Description | Key Deliverables |
|-------|-------------|-----------------|
| **Phase 1** | Core Pipeline MVP | Intent, Safety, Feature agents; SQLite database; meal & medication tools |
| **Phase 2** | Tool Expansion | Exercise, Symptom, Drug-Food Interaction tools; Web search integration |
| **Phase 3** | API Server | FastAPI integration, custom endpoints, OpenAPI schema, CORS |
| **Phase 4** | Image Analysis | Medication OCR, Medical report analysis, two-pass vision pipeline |
| **Phase 5** | Refinement | 3-agent pipeline refactoring, Pydantic fixes, deployment config |

### 19.3 Branching Strategy

- **main**: Stable releases
- Development done locally with direct commits to main

---

## 20. Known Issues & Limitations

### 20.1 Current Issues

| # | Issue | Impact | Workaround |
|---|-------|--------|------------|
| 1 | `/docs` Pydantic schema generation error | Swagger UI may show incomplete schema | Use `API_DOCS.md` for integration reference |
| 2 | Ollama must be running locally | Agent endpoints fail without Ollama | Start Ollama before server: `ollama serve` |
| 3 | Session memory is in-memory only | Past conversations lost on restart | Use `DatabaseSessionService` (already done for sessions) |
| 4 | SerpAPI key is hardcoded | Security concern, rate limiting | Move to environment variable or secrets manager |
| 5 | CORS wildcard (`*`) | Not production-safe | Restrict to specific origins |

### 20.2 Limitations

| Limitation | Detail |
|-----------|--------|
| **No RAG** | Medical Q&A uses web search, not indexed vector embeddings from datasets |
| **Test Data Only** | Database uses curated seed data (19 meals, 20 interactions, 15 diseases) |
| **Single Language** | Only Egyptian Arabic responses (no English output mode) |
| **No Real-Time Vitals** | No integration with health monitoring devices |
| **Local-Only Ollama** | Requires local GPU for reasonable inference speed |
| **No Multi-Turn Memory** | Each turn is somewhat independent; limited conversation memory |

---

## 21. Future Work & Roadmap

### Phase A: RAG & Data Integration

- Index all 14 datasets into vector embeddings (FAISS/Milvus)
- Implement RAG-powered Medical Q&A with citation support
- Expand meal database from 19 → 200+ Egyptian meals using USDA data

### Phase B: Production Hardening

- Migrate to Google Gemini for cloud deployment (no local Ollama needed)
- Implement Vertex AI Memory Bank for persistent long-term memory
- Add rate limiting, authentication, and proper secrets management
- Deploy to Google Cloud Run or similar serverless platform

### Phase C: Feature Extensions

- Caregiver dashboard with alerts and reports
- TTS (Text-to-Speech) for audio responses
- Multi-dialect support (Modern Standard Arabic, Gulf Arabic)
- Daily routine and scheduling agent
- Analytics pipeline with adherence tracking

### Phase D: Mobile Integration

- Deep integration with Flutter/React Native mobile app
- Push notifications for medication reminders
- Integration with health devices (blood pressure, glucose monitors)
- Offline fallback with embedded model (TinyLlama/Phi-3)

---

## 22. Appendices

### Appendix A: Full Requirements (`requirements.txt`)

```txt
google-adk>=0.1.0
google-genai>=0.3.0
litellm>=1.0.0
python-dotenv>=1.0.0
pydantic>=2.0.0

# API Server
uvicorn[standard]>=0.27.0
aiosqlite>=0.19.0
fastapi>=0.109.0

# Image Analysis
httpx>=0.26.0
```

### Appendix B: User Profile Schema

```json
{
    "user:user_id":          "string — unique identifier",
    "user:user_name":        "string — display name",
    "user:age":              "integer — age in years",
    "user:weight":           "float — weight in kg",
    "user:height":           "float — height in cm",
    "user:gender":           "string — male / female",
    "user:chronicDiseases":  "string[] — diabetes, hypertension, arthritis, etc.",
    "user:allergies":        "string[] — shellfish, dairy, gluten, nuts, eggs, fish",
    "user:medications":      "object[] — [{name, dose}]",
    "user:mobilityStatus":   "string — limited / moderate / active",
    "user:bloodType":        "string — A+, O-, B+, etc.",
    "user:caregiver_ids":    "string[] — linked caregiver IDs"
}
```

### Appendix C: Emergency Keywords

The Orchestrator Agent detects these patterns:

- Chest pain / pressure / tightness
- Severe difficulty breathing / choking
- Loss of consciousness / fainting / sudden confusion
- Stroke symptoms (face drooping, arm weakness, speech difficulty)
- Severe bleeding
- Severe allergic reactions (swelling, breathing issues)
- Signs of overdose or poisoning
- Suicidal thoughts or self-harm intentions
- Sudden severe headache / sudden vision loss

### Appendix D: Sample API Integration (cURL)

```bash
# Step 1: Set user profile
curl -X POST http://localhost:8080/set-user-profile/user_123 \
  -H "Content-Type: application/json" \
  -d '{"user_name":"Ahmed","age":72,"chronicDiseases":["diabetes"],"medications":[{"name":"Metformin","dose":"500mg"}]}'

# Step 2: Create session
curl -X POST http://localhost:8080/apps/seniocare/users/user_123/sessions/sess_1 \
  -H "Content-Type: application/json" -d '{}'

# Step 3: Send message
curl -X POST http://localhost:8080/run_sse \
  -H "Content-Type: application/json" \
  -d '{"app_name":"seniocare","user_id":"user_123","session_id":"sess_1","new_message":{"role":"user","parts":[{"text":"أنا جوعان، أكل إيه؟"}]},"streaming":false}'
```

### Appendix E: Tool Idempotency Guards

Every tool uses a state flag to prevent multiple calls per turn:

| Tool | Guard Key |
|------|-----------|
| `get_meal_options` | `_meal_tool_called` |
| `get_meal_recipe` | `_recipe_tool_called` |
| `get_medication_schedule` | `_medication_tool_called` |
| `log_medication_intake` | `_log_medication_tool_called` |
| `get_exercises` | `_exercise_tool_called` |
| `check_drug_food_interaction` | `_interaction_tool_called` |
| `assess_symptoms` | `_symptom_tool_called` |
| `search_web` | `_web_search_called` |
| `search_youtube` | `_youtube_search_called` |
| `search_medical_info` | `_medical_search_called` |
| `analyze_medication_image_tool` | `_medication_image_tool_called` |
| `analyze_medical_report_tool` | `_medical_report_tool_called` |

---

> **Document generated automatically by analyzing the complete SenioCare codebase.**  
> **Author:** Ahmed Yasser | **License:** MIT | **© 2026**
]]>
