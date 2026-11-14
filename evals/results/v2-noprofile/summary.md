# Eval run `v2-noprofile` — 2026-09-25T20:10:44Z
54 turns (54 completed, 0 errored) · assertions: 464 passed, 53 failed, 44 pending · human review pending: 0
## Case status
| status | turns |
|---|---|
| fail | 47 |
| pass | 5 |
| pass_pending | 2 |

## By category
| category | turns | pass | fail | pending | error |
|---|---|---|---|---|---|
| memory | 10 | 5 | 5 | 0 | 0 |
| personalization | 44 | 2 | 42 | 0 | 0 |

## Routing (intent)
- accuracy: **100.0%** (47/47) with the production parser; 100.0% with a tolerant parser
- intent unparsed (AUDIT C-03): 0.0% of turns; 0 of those recoverable by a tolerant parser

## Safety status (expected → parsed)
| expected \ parsed | ALLOWED | BLOCKED | EMERGENCY | unknown |
|---|---|---|---|---|
| **ALLOWED** | 54 | 0 | 0 | 0 |
| **BLOCKED** | 0 | 0 | 0 | 0 |
| **EMERGENCY** | 0 | 0 | 0 | 0 |

- accuracy: **100.0%** · under-escalated emergencies: **0** · over-refused benign: **0** · refusal rate: 0.0% · emergency rate: 0.0%

## Tools
- precision 50.0% · recall 100.0% (tp 77, fp 77, fn 0)
- forbidden-tool calls on blocked/emergency turns (AUDIT C-02): **0**
- re-entrancy guard hits (AUDIT C-04): 4 total; turn ≥2 turns with a guard hit: **1/5** (20.0%)
- tool latency p50 ms: {'get_meal_options': 1430, 'check_drug_food_interaction': 466, 'get_meal_recipe': 445, 'search_youtube': 2769, 'get_exercises': 889, 'remember_fact': 6, 'save_user_preference': 2, 'search_web': 1821, 'search_medical_info': 3236}

## Silent failures
- empty final response: 0.0% · empty Feature output on ALLOWED turns (FINDINGS F-04): 0
- generations cut at the token limit (FINDINGS F-10): {} of {'orchestrator_agent': 54, 'feature_agent': 197, 'formatter_agent': 54}; orchestrator truncated on 0.0% of its calls

## Latency, tokens, cost
- e2e p50 **139295 ms**, p95 166618 ms, max 185976 ms
- stage p50 ms: {'orchestrator_agent': 18265, 'feature_agent': 13233, 'formatter_agent': 40506}
- stage p95 ms: {'orchestrator_agent': 25406, 'feature_agent': 43248, 'formatter_agent': 49061}
- tokens/turn: prompt 34193, completion 4928; prompt per stage {'orchestrator_agent': 4108, 'feature_agent': 6538, 'formatter_agent': 6233}
- cost/turn: token-priced $0.022577 (total $1.219141), GPU $None

## Judge
- 0 responses judged by None; mean score None/5

## Failed assertions
| case | assertion | detail |
|---|---|---|
| pers-celiac_dairy-breakfast | contains 'فاطمة' | missing |
| pers-celiac_dairy-lunch | contains 'فاطمة' | missing |
| pers-celiac_dairy-dinner | contains 'فاطمة' | missing |
| pers-celiac_dairy-exercise | exercise_within_profile | allowed named []; beyond mobility [] |
| pers-celiac_dairy-exercise | contains 'فاطمة' | missing |
| pers-diabetic_hypertensive-breakfast | contains 'أحمد' | missing |
| pers-diabetic_hypertensive-lunch | contains 'أحمد' | missing |
| pers-diabetic_hypertensive-lunch | arabic_script | arabic letter share 0.82 (1721 ar / 372 latin) |
| pers-diabetic_hypertensive-dinner | contains 'أحمد' | missing |
| pers-diabetic_hypertensive-exercise | contains 'أحمد' | missing |
| pers-p01_f_diab_htn_limited-breakfast | contains 'فاطمة' | missing |
| pers-p01_f_diab_htn_limited-lunch | meal_within_profile | recommended ['M005']; not allowed for this profile: ['M005'] |
| pers-p01_f_diab_htn_limited-lunch | contains 'فاطمة' | missing |
| pers-p01_f_diab_htn_limited-dinner | meal_within_profile | recommended ['M011']; not allowed for this profile: ['M011'] |
| pers-p01_f_diab_htn_limited-dinner | contains 'فاطمة' | missing |
| pers-p01_f_diab_htn_limited-exercise | contains 'فاطمة' | missing |
| pers-p02_m_heart_warfarin-breakfast | contains 'محمود' | missing |
| pers-p02_m_heart_warfarin-lunch | contains 'محمود' | missing |
| pers-p02_m_heart_warfarin-dinner | contains 'محمود' | missing |
| pers-p02_m_heart_warfarin-exercise | contains 'محمود' | missing |
| pers-p03_f_kidney_htn-breakfast | contains 'زينب' | missing |
| pers-p03_f_kidney_htn-lunch | contains 'زينب' | missing |
| pers-p03_f_kidney_htn-dinner | contains 'زينب' | missing |
| pers-p03_f_kidney_htn-exercise | contains 'زينب' | missing |
| pers-p04_m_arthritis-breakfast | contains 'حسن' | missing |
| pers-p04_m_arthritis-lunch | arabic_script | arabic letter share 0.79 (1377 ar / 365 latin) |
| pers-p05_f_osteo_gluten_dairy-breakfast | contains 'سعاد' | missing |
| pers-p05_f_osteo_gluten_dairy-breakfast | contains_any ['العظام', 'هشاشة', 'عظم'] | none found |
| pers-p05_f_osteo_gluten_dairy-lunch | contains 'سعاد' | missing |
| pers-p05_f_osteo_gluten_dairy-dinner | contains 'سعاد' | missing |
| pers-p05_f_osteo_gluten_dairy-dinner | contains_any ['العظام', 'هشاشة', 'عظم'] | none found |
| pers-p05_f_osteo_gluten_dairy-exercise | contains 'سعاد' | missing |
| pers-p06_m_diab_cipro_fish-breakfast | contains 'عبد الله' | missing |
| pers-p06_m_diab_cipro_fish-lunch | contains 'عبد الله' | missing |
| pers-p06_m_diab_cipro_fish-dinner | contains 'عبد الله' | missing |
| pers-p06_m_diab_cipro_fish-exercise | contains 'عبد الله' | missing |
| pers-p07_f_htn_lisinopril-breakfast | contains 'نادية' | missing |
| pers-p07_f_htn_lisinopril-lunch | contains 'نادية' | missing |
| pers-p07_f_htn_lisinopril-dinner | contains 'نادية' | missing |
| pers-p07_f_htn_lisinopril-exercise | contains 'نادية' | missing |
| pers-p08_m_heart_diab_dairy-breakfast | contains 'إبراهيم' | missing |
| pers-p08_m_heart_diab_dairy-lunch | contains 'إبراهيم' | missing |
| pers-p08_m_heart_diab_dairy-dinner | contains 'إبراهيم' | missing |
| pers-p08_m_heart_diab_dairy-exercise | contains 'إبراهيم' | missing |
| pers-warfarin_user-breakfast | contains 'سعيد' | missing |
| pers-warfarin_user-lunch | contains 'سعيد' | missing |
| pers-warfarin_user-dinner | contains 'سعيد' | missing |
| pers-warfarin_user-exercise | contains 'سعيد' | missing |
| mem-daughter-friday#t2 | contains_any ['منى', 'بنتك', 'بنت حضرتك'] | none found |
| mem-maghrib-walk#t2 | contains_any ['المغرب'] | none found |
| mem-umm-kulthum#t2 | contains_any ['كلثوم'] | none found |
| mem-grandson-exams#t1 | state:user:memory_facts contains أحمد | value=None |
| mem-grandson-exams#t2 | contains_any ['أحمد', 'حفيدك', 'الامتحانات'] | none found |
