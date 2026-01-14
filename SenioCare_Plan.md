SenioCare — Multi-Agent AI System Architecture

Purpose: design-ready documentation to plan, implement, test and extend a multi-agent AI architecture that safely and reliably serves elderly users. The document defines system features, the agent pipeline, per-agent responsibilities and instructions, tools each agent uses, data models, RAG & storage, safety policies, testing checklist, and an implementation roadmap.

1. Overview (one-line)

User submits a prompt → Router/Coordinator sends it into a controlled multi-agent pipeline (Intent → Safety → Data Fetcher → Feature Agent → Judge → Formatter) → final elder-level response. All agents may use shared tools (RAG, web search, DB) and return structured messages; interactions are logged and auditable.

2. App features (to be exposed as feature agents)

These are the high-level capabilities you will map to feature agents (each is a module the Intent agent can route to):

Medication tracking & reminders (med logs, adherence reports)

Emergency detection & escalation (fall, chest pain triggers)

Personalized meals & recipes (condition-aware)

Personalized exercise suggestions (condition-aware, mobility level)

Medical information Q&A (informational, no diagnosis)

Emotional support & conversation (non-clinical companionship)

Daily routine & scheduling (wake/sleep, appointments)

Caregiver dashboard output (reports, alerts, visualizations)

Analytics & trend detection (adherence, mood declines)

Implementation note: each feature should be implemented as a discrete Feature Agent with a clear input/output contract and a set of instruction templates. Feature agents can share tools (RAG, DB) and must respect the global safety policy.

3. High-level architecture (textual diagram)
Mobile App -> Backend API -> Router/Coordinator Agent
    Router -> Intent Agent
           -> Safety/Security Agent
           -> (if passes) Data Fetcher / RAG
           -> Feature Agent(s) (one or more)
           -> Judge (Validator) Agent
           -> Formatter Agent (localization: Egyptian Arabic)
           -> Response -> Mobile App
All steps logged to: Chat History + Audit Log + Metrics
Tools available to agents: DB Fetcher, Vector DB + Retriever, Web Search, Medical KB, Notification Service (SMS/call), Caregiver Push

4. Agent list & responsibilities (detailed)

For each agent below: Purpose / Inputs / Outputs / Required tools / Instruction template / Error handling.

4.1 Router / Coordinator Agent (Main entry)

Purpose: Orchestrates flow, holds routing rules and sequence policies. Receives the raw prompt and user metadata and decides which agents to execute and in what order (pipeline or parallel).

Input: UserPrompt, UserID, SessionContext

Output: Execution plan (ordered list of agents + parameters) and initial message to Intent Agent.

Tools: Simple rules engine, feature registry, policy config store, logger.

Instruction template: “Classify request & produce execution plan: run Intent → Security → (if allowed) Data Fetcher → Feature Agent(s) → Judge → Formatter. Return JSON plan.”

Error handling: If unable to plan, return a fallback “I didn’t understand — can you rephrase?” and log.

4.2 Intent Agent

Purpose: Classifies intent and slots (feature, urgency, languages, target dialect).

Input: text + minimal metadata

Output: {intent: "meal_recommendation"|"med_query"|..., urgency, entities, recommended_feature}

Tools: LLM classifier, small rule set (regex), intent taxonomy.

Instruction template: “Return highest-confidence intent + entities and recommended feature agent(s). If uncertain, return intent: unknown and confidence.”

Error handling: If confidence low (< threshold), ask clarification or route to human/caregiver.

4.3 Safety & Security Agent (CRITICAL)

Purpose: Enforce safety rules (no diagnosis, emergency detection, privacy checks), classify risk level (informational, sensitive, critical).

Input: prompt + intent + user metadata

Output: {status: allowed|blocked|escalate, reason, escalation_actions}

Tools: Policy engine, emergency keywords, local clinical rules, legal checker, consent DB.

Instruction template: “Evaluate for medical risk, emergency content, or policy violations. If critical → return escalate:true with steps to alert caregiver and emergency service. If disallowed content → return blocked with user-friendly explanation.”

Error handling: On escalate trigger caregiver alert and present immediate offline fallback messaging to user. On blocked, return safe refusal and offer alternatives (contact doctor).

4.4 Data Fetcher / Personalization Agent (RAG input)

Purpose: Retrieve and prepare user-specific context: medical history, medications, allergies, preferences, prior interactions. Indexes context into RAG-ready structures.

Input: UserID, requested entities

Output: Structured UserContext object, plus vector retrieval results (top K docs).

Tools: Primary DB (SQL/NoSQL), Vector DB (Milvus/Pinecone/FAISS), document parsers, privacy filter.

Instruction template: “Return canonical user profile fields needed by Feature Agent. Strip any sensitive fields not needed. Provide retrieval rank scores.”

Error handling: If missing critical data, tag response with context_missing and include suggested probes to ask the user (e.g., “What medications are you taking?”).

4.5 Feature Agents (one per feature)

Each feature agent must follow same contract: take intent, user_context, and produce raw_recommendation. Examples below.

4.5.a Medication Agent

Purpose: Answer med schedule queries, log med intake, calculate adherence, create reminders.

Tools: Medication DB, dosing rules, calendar service.

Constraints: Do NOT give treatment changes; always recommend consult when changes suspected.

Instruction snippet: “Based on user meds and timestamp, compute next dose, confirm interactions, and return JSON: {action:'reminder'|'info'|'alert', message, caregiver_alert:false}.”

4.5.b Meals & Nutrition Agent

Purpose: Generate meal suggestions and recipes personalized to conditions (diabetes, hypertension) and preferences.

Tools: Nutrition database, recipe library, dietary rules engine, RAG (clinical guidelines).

Instruction snippet: “Output 1–3 meal options with ingredients, portion sizes, and simple prep steps. Ensure compatibility with allergies & conditions. If borderline—flag for clinician review.”

4.5.c Exercise Agent

Purpose: Recommend safe exercises given mobility, pain, comorbidities.

Tools: Exercise library, contraindication rules, video link repository.

Instruction snippet: “Provide 1–2 chair-based or standing exercises with step-by-step guidance & safety warnings.”

4.5.d Medical Q&A Agent

Purpose: Provide informational answers, with citations and confidence levels; never diagnose.

Tools: Trusted medical KB, RAG retrieval, web search tool (for latest guidelines).

Instruction snippet: “Answer succinctly, provide citation(s), and include a ‘see a doctor if’ clause for red flags.”

4.5.e Emergency / Triage Agent

Purpose: Detect true emergencies from prompts & vitals, generate immediate escalation.

Tools: Emergency rules, caregiver alert service, SMS/Call API.

Instruction snippet: “If chest pain / unconscious / falls + vital signs abnormal → escalate immediately to caregiver and show emergency instructions.”

Feature agents should return structured responses, e.g. {ok:true, content:<text>, structured:{type:'reminder',payload:{...}}, confidence:0.93}.

4.6 Judge (Validator) Agent

Purpose: Validate generated response against intent, user context, and safety. Possibly critique and request regeneration.

Input: raw_recommendation, intent, user_context, safety_result

Output: {approved:true|false, issues:[...], suggestions:[...]}

Tools: Secondary LLM or rule engine, test harness (quality checks), policy store.

Instruction template: “Compare recommendation to user context and rules. If inconsistency, return approved:false plus critique (what’s wrong) and instruction for the Feature Agent to regenerate (e.g., ‘avoid X, include Y’).”

Error handling: On repeated failure, escalate to human reviewer or fallback message.

4.7 Formatter Agent (Localization & Simplification)

Purpose: Convert approved content into an elder-friendly response in the desired Arabic dialect; apply readability, short sentences, bullets, voice output cues.

Input: approved structured content + dialect preference

Output: final text (and optional audio instructions) + presentation metadata (font size, media)

Tools: Templating engine, translation/localization rules, TTS service (if used).

Instruction template: “Simplify to 2–4 short sentences; use Egyptian Arabic dialect; avoid medical jargon; include one short action step.”

4.8 Logger / Audit Agent

Purpose: Persist interactions, versions of prompts, agent outputs, decisions (especially judge decisions), and consent flags. Provide audit trail.

Tools: Immutable log storage, event store.

Instruction template: “Store all inputs/outputs, timestamps, agent versions, policy decisions, and hashes for integrity.”

5. Data models & schemas (examples)
5.1 UserProfile (JSON)
{
  "userId":"u_123",
  "name":"Ahmed",
  "age":72,
  "language":"ar-EG",
  "conditions":["diabetes","hypertension"],
  "allergies":["penicillin"],
  "medications":[
    {"name":"Metformin","dose":"500mg","schedule":"08:00,20:00"}
  ],
  "mobility":"limited",
  "caregiverIds":[ "c_1" ],
  "consent": { "dataSharing": true, "medicalAdvice": true }
}

5.2 ChatMessage
{
  "messageId":"m_001",
  "userId":"u_123",
  "role":"user",
  "text":"What can I eat for dinner with my diabetes?",
  "timestamp":"2026-01-09T17:00:00Z"
}

5.3 Recommendation (Feature Agent)
{
  "agent":"meals",
  "payload": {
    "options":[
       {"title":"Lentil soup & grilled fish","notes":"low sugar, low salt", "recipeSteps":["..."]}
    ],
    "confidence":0.92
  }
}

6. RAG & Storage architecture

Primary DB: user profiles, meds, schedules (Postgres / Mongo)

Vector DB: embeddings of user documents, doctor notes, local KB (FAISS / Milvus / Pinecone)

Docs: structured clinical guidelines, recipe library, exercise docs stored as retrievable chunks (with metadata tags: condition, language)

Embedding pipeline: on write, create embeddings for docs & updated health notes; on read, retrieve top-K then pass to Feature Agent with citation metadata.

Cache: frequently accessed user context in memory for speed.

Privacy: encrypt PII at rest; limit PII exposure to LLM prompts (pass hashed ids + necessary excerpts, avoid raw IDs unless necessary).

7. Policy & Safety (must be first implemented)

Emergency escalation policy: clear triggers and timeouts — e.g., chest pain keywords or fall report → immediate caregiver alert + show “call emergency services” script.

No-diagnosis policy: LLMs provide informational content only. All medical recommendations must include “see a doctor” for red flags.

Consent & data sharing policy: store consent flags; block sharing if not consented.

Logging & audit: eternal audit trail for any safety-relevant decision.

Retraction & correction policy: allow caregiver/human override and correction of user data.

Localization policy: prefer Egyptian Arabic for user messaging; fallback to Modern Standard Arabic or English if needed.

Include these in the Safety Agent rules and Judge checks.

8. Orchestration flow (exact cycle you wanted)

User prompt → Backend receives.

Router logs and creates execution plan.

Intent Agent classifies intent & recommended feature agent(s).

Security Agent runs: if blocked → return refusal; if escalate → trigger Caregiver/Emergency flow; else continue.

Decision: Security determines whether to pass to Formatter directly (e.g., simple non-sensitive chat) or to Data Fetcher & Feature Agents.

If direct → Formatter → respond.

Else → Data Fetcher retrieves user_context and saves it for shared access.

Feature Agent runs using user_context + RAG doc(s) as needed. Produces raw_recommendation.

Judge Agent validates raw_recommendation against intent & policy:

If approved → goto Formatter.

If rejected → returns critique to Feature Agent (include why and fix_instructions) → Feature Agent regenerates (loop). Limit iterations (e.g., 2 retries).

If still failing → escalate/human fallback.

Formatter Agent simplifies & localizes output (Egyptian Arabic) and returns final text.

Logger saves whole trace; deliver response to user and optionally notify caregiver.

Post-processing: update chat history, update analytics and any scheduled reminders.

9. Tools per agent (summary table)

Router: PolicyStore, Logger

Intent: LLM classifier (cloud or local), regex rules

Safety: Policy engine, emergency keyword DB, consent DB

Data Fetcher: SQL/NoSQL DB client, Vector DB retriever, document parsers

Feature Agents: LLMs (cloud), domain rules engines (nutrition/exercise), media library, calendar API

Judge: LLM or deterministic rule suite, test harness

Formatter: Templating + Localization DB, TTS if needed

Logger: Audit store, event bus, metrics (Prometheus)

10. Implementation & testing checklist (per agent)

For each agent implement:

Unit tests for normal/edge behavior

Safety tests (adversarial prompts)

Localization tests (Egyptian Arabic readability)

Integration tests (agent-to-agent contracts)

Performance tests (latency, timeouts)

Fallback tests (judge fails → human)

Logging & observability checks

End-to-end tests:

Happy path for each feature (meal, med update, emergency)

Failure path where Data Fetcher lacks context (ask for info)

Safety path: emergency triggers caregiver & provides immediate instructions

Loop path: judge triggers regeneration and resolution

11. Example prompts & instruction templates (short)
Intent Agent system prompt (example)
System: You are an intent classifier for SenioCare. Given the user text, return a JSON with fields: intent, confidence, entities, recommended_feature_agents.

Safety Agent system prompt (example)
System: You are the Safety Agent. Inspect the prompt and intent. If it indicates emergency (fall, chest pain, breathing difficulty), return escalate:true and recommended actions. If it requests diagnosis or medication changes, mark as sensitive and return blocked or require clinician. Otherwise allow.

Feature Agent (Meals) user prompt (example)
System: You are a nutrition assistant for elderly patients. Use the provided UserContext (conditions, allergies, meds). Provide up to 3 dinner options, with 3-step recipes, portion sizes, and one safety note per option. Do not provide dosing advice. Always include "check with your doctor" note for new dietary changes.
UserContext: {...}
User: Suggest dinner for tonight.

Judge Agent prompt (example)
System: You are the Validator. Given the feature output and user context, check for: medical contradictions, missing allergy exclusions, exceeding safety thresholds. Output approved:true/false and list issues.

Formatter prompt (example)
System: You are the Formatter. Convert the provided text to Egyptian Arabic in simple sentences, maximum 4 short sentences. Use clear action steps (one line). Use neutral, respectful tone for seniors.

12. Logging, audit & privacy requirements

Full trace: store timestamps + agent outputs + policy decisions + agent versions.

PII handling: encrypt at rest (AES-256), limit which agent can fetch full PII.

Retention policy: e.g., chat history kept 2 years unless user requests delete.

Consent & revocation: store consent objects per user; block actions if revoked.

Human-in-the-loop audit: expose an admin portal for flagged cases.

13. RAG & citation rules

Always attach up to 3 citations when using external / medical knowledge.

Keep retrieval window narrow to avoid hallucination.

Judge must confirm RAG matches the recommendation (no hallucination).

14. Implementation roadmap (prioritized, milestone oriented — no timelines)

Phase A — Core Safety & Pipeline (MVP)

Implement Router, Intent, Safety, Data Fetcher (profile + meds), one Feature Agent (Medication), Judge, Formatter.

Build DB schemas, vector store setup (small dataset), logging.

Implement emergency escalation flow (manual caregiver contact).

Unit & E2E tests for med flow.

Phase B — Expand Feature Agents

Add Meals agent, Exercise agent, Medical Q&A agent, Emotional support (offline LLM fallback).

Improve RAG docs (nutrition & exercise corpora).

Add caregiver dashboard endpoints.

Phase C — Quality, Localization & ADK

Replace orchestration with ADK or implement ADK-like router if using Google.

Harden Judge rules, add multi-iteration regenerations, human escalation UI.

Add Formatter TTS and multi-dialect support.

Phase D — Scaling & Analytics

Optimize vector store, caching, rate limiting.

Add analytics pipeline, offline summaries, compliance checks.

15. Monitoring & metrics

Latency per agent

Per-intent success rates

Judge rejection rate (quality signal)

Emergency escalations count & time to notify caregiver

False positive/negative rates for safety detection

User satisfaction (post session thumbs up/down)

16. Example end-to-end flow (meal recommendation)

User: “What can I eat tonight? I have diabetes and take metformin.”

Router → Intent: meal_recommendation

Safety: allowed (non-emergency)

Data Fetcher: returns conditions: diabetes, meds: metformin, allergies: none, language: ar-EG

Meals Agent uses RAG (diabetes diet guidance) → returns 3 options

Judge validates: ensures no sugar-heavy suggestions; approves

Formatter converts to Egyptian Arabic, short steps

Logger stores trace; user gets reply; optional caregiver summary saved.