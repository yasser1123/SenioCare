# SenioCare: Experiment protocol v2 (safety-first companion)

This protocol follows `docs/EXPERIMENTS.md`, which covered runs A, A′ and C. The code under test is the `feat/hardening` branch at or after commit 2e5d1f8. The findings behind each change are F-14, F-15 and F-16 in `docs/FINDINGS.md`.

## 1. Questions

| # | Question | Measured by |
|---|---|---|
| RQ1 | Does the safety layer make what the user reads safe? | Emergency number first, foreign numbers, self-harm reply, missing-image handling, emergency latency. Full run vs `SENIOCARE_SAFETY_LAYER=0`. |
| RQ2 | Does showing the model the profile make answers personal and correct? | Meal and exercise within the profile's allowed set, medicines outside the profile, name, condition-aware advice. Full run vs `SENIOCARE_PROFILE_IN_PROMPT=0`. |
| RQ3 | Does the assistant remember across conversations? | Memory recall in a new session (`10_memory`). |
| RQ4 | Is it stable? | Pass rate and pass^k over repeated full runs. |
| — | Continuity with runs A, A′ and C | The original 60 turns (files 01–06) are unchanged and part of every full run. |

## 2. Test set v2 (frozen once the first scored run starts)

| File | Turns | What it tests |
|---|---|---|
| 01–06 (original) | 60 | As in runs A, A′ and C |
| 07_personalization | 44 | 11 personas × breakfast, lunch, dinner and exercise; ground truth from the knowledge-base seeds (`generate_personalization_cases.py`) |
| 08_safety_v2 | 31 | 10 emergencies, 5 self-harm, 8 blocked, 8 benign look-alikes |
| 09_images | 8 | 6 synthetic medicine boxes and reports (`make_images.py`), 2 missing-image turns |
| 10_memory | 10 | 5 two-session scenarios |
| **Total** | **153** | |

Do not edit a case after its first scored run. If a case turns out to be wrong, add a corrected copy with a new id and report both.

## 3. Model: why gemma4:e4b on Colab, and why not Qwen on the laptop

- **Scored runs: `gemma4:e4b` on a Colab T4, the same model as runs A, A′ and C.** Only on this model are the results comparable with the earlier runs and the paper's hardening story. Start the server with `OLLAMA_CONTEXT_LENGTH=16384`, and record `/api/ps` and the model digest.
- **The laptop's `qwen3:0.6b` / `qwen2.5:0.5b` is for wiring checks only.** The laptop has a GTX 1650 with 4 GB. These models are about 8× smaller, misroute most turns and invent profile details. Their numbers say nothing about the system. They are useful for checking that code, harness and cases run end to end in minutes (see §6).
- **Optional second model:** one full run with `qwen3:8b` (or `qwen3:4b`) on the same Colab T4. This tests whether the safety layer and profile checks hold across models, which answers the "one model only" limitation. Do it only after the runs in §5.

## 4. Before the first scored run (user steps)

1. **Search key.** Create a free Tavily account at https://app.tavily.com and copy the API key. Put these lines in `.env`, never in git:
   ```
   TAVILY_API_KEY=tvly-...
   SEARCH_CACHE_DIR=evals/search_cache
   ```
   The cache makes every later run see the same search results and spend no credits. The first full run uses roughly 40–60 searches; the Tavily free tier is 1,000 credits a month (check the current limit on their site). A YouTube Data API key is optional.

   Then check the key:
   ```
   python -c "from seniocare.tools.web_search import provider,search_medical_info;print(provider());print(search_medical_info('diabetes diet',type('C',(),{'state':{}})())['status'])"
   ```
   It should print `tavily` and `success`.
2. **Model server.** Open `colab/SenioCare_Model_Server.ipynb` on a T4 and start Ollama with `OLLAMA_CONTEXT_LENGTH=16384`. Copy the tunnel URL into `.env` as `MODEL_API_BASE=.../v1`, keeping the same `MODEL_NAME` as runs A′ and C. Run `python scripts/check_model.py` (the `check_model` gate).
3. `EVAL_TURN_TIMEOUT_S=600` (as in runs A′ and C).
4. Run one run at a time. Runs A′ and C overlapped on one GPU, which confounded latency; do not repeat that.

## 5. Runs, in priority order

Every command runs on the laptop, from the repo root. The model runs on Colab. If the tunnel drops, restart it, update `MODEL_API_BASE`, and re-run the same command with `--resume`.

| Run | Command | Turns | Est. time |
|---|---|---|---|
| **D1** full, all on | `python evals/runner.py --name v2-full-r1` | 153 | 5–6 h |
| **F** no profile in prompt | `SENIOCARE_PROFILE_IN_PROMPT=0 python evals/runner.py --cases evals/cases/07_personalization.jsonl,evals/cases/10_memory.jsonl --name v2-noprofile` | 54 | 2–2.5 h |
| **E** no safety layer | `SENIOCARE_SAFETY_LAYER=0 python evals/runner.py --cases evals/cases/04_emergency.jsonl,evals/cases/08_safety_v2.jsonl,evals/cases/09_images.jsonl --name v2-nolayer` | 46 | 1.5–2 h |
| **D2**, **D3** repeats | `python evals/runner.py --cases evals/cases/07_personalization.jsonl,evals/cases/08_safety_v2.jsonl,evals/cases/09_images.jsonl,evals/cases/10_memory.jsonl --name v2-core-r2` (then `-r3`) | 93 each | 3.5 h each |
| G (optional) second model | as D1 with `MODEL_NAME` set to the Qwen model, `--name v2-full-qwen` | 153 | ~5 h |

On Windows PowerShell, set a switch with `$env:SENIOCARE_SAFETY_LAYER="0"` before the command, and remove it afterwards with `Remove-Item Env:SENIOCARE_SAFETY_LAYER`.

Each run writes `evals/results/<name>/` containing `results.jsonl`, `summary.json`, `summary.md`, `config.json` and `human_review.csv`. `config.json` records the switches, the search provider and the timeout.

## 6. Smoke check before each Colab session (laptop, minutes)

```
ollama serve        # in its own terminal
MODEL_NAME=ollama_chat/qwen3:0.6b MODEL_API_BASE=http://localhost:11434 \
  python evals/runner.py --cases evals/cases/08_safety_v2.jsonl --limit 5 --out /tmp/smoke --name smoke
pytest -q && pytest -q tests_adk
```

## 7. Analysis

- **Proportions:** exact Clopper–Pearson 95% CIs.
- **Paired comparisons** (full vs ablation, turn by turn on the same cases): exact McNemar. This is the same analysis as the paper's current tables; the script is `docs/paper/build/stats.py`, extended to the v2 metrics.
- **Repeats:** per-case pass rate and pass^3.
- **Content safety:** from `summary.json → content_safety`.
- **Personalisation:** from the `meal_within_profile`, `exercise_within_profile`, `no_unlisted_medications` and name/condition assertions.
- **Human review:** `human_review.csv` in each run. Two native Egyptian-Arabic speakers from outside the team rate a stratified sample of replies. They score safety, helpfulness and dialect on a 1–5 scale, blind to configuration; report Cohen's κ. A clinician is not required for this; it is reported as a limitation.

## 8. Threats specific to v2

- The personalisation ground truth follows the knowledge base's own rules. It measures whether the pipeline respects its knowledge base, not whether that knowledge base is clinically complete.
- The safety cases were written by the developers, and the passive self-harm screen patterns were written after the self-harm cases (F-15). Report the screen's hit rate on the original 60 turns as the less-biased figure.
- The images are synthetic renders, which are cleaner than phone photos.
- Search results come from the cache after the first run: identical across runs, but frozen in time.
