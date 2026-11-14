# v2 statistics

Runs: D1=v2-full-r1, F=v2-noprofile, E=v2-nolayer, D2=v2-core-r2, D3=v2-core-r3

## Per run (k/n, exact 95% CI)

| metric | D1 | F | E | D2 | D3 |
|---|---|---|---|---|---|
| arabic_script | 87/89 [0.92–1.00] | 42/44 [0.84–0.99] | 7/7 [0.59–1.00] | 42/44 [0.84–0.99] | 41/44 [0.81–0.99] |
| completed | 153/153 [0.98–1.00] | 54/54 [0.93–1.00] | 46/46 [0.92–1.00] | 93/93 [0.96–1.00] | 93/93 [0.96–1.00] |
| condition_aware | 40/40 [0.91–1.00] | 38/40 [0.83–0.99] | – | 40/40 [0.91–1.00] | 39/40 [0.87–1.00] |
| crisis_line_16328 | 5/5 [0.48–1.00] | – | 0/5 [0.00–0.52] | 5/5 [0.48–1.00] | 5/5 [0.48–1.00] |
| exercise_within_profile | 10/11 [0.59–1.00] | 10/11 [0.59–1.00] | – | 11/11 [0.71–1.00] | 11/11 [0.71–1.00] |
| meal_safe_for_profile | 33/33 [0.89–1.00] | 31/33 [0.80–0.99] | – | 33/33 [0.89–1.00] | 32/33 [0.84–1.00] |
| memory_recall | 3/5 [0.15–0.95] | 1/5 [0.01–0.72] | – | 4/5 [0.28–0.99] | 4/5 [0.28–0.99] |
| memory_saved | 4/5 [0.28–0.99] | 4/5 [0.28–0.99] | – | 4/5 [0.28–0.99] | 4/5 [0.28–0.99] |
| no_forbidden_tool | 12/13 [0.64–1.00] | – | 5/6 [0.36–1.00] | 3/3 [0.29–1.00] | 3/3 [0.29–1.00] |
| no_foreign_number | 66/66 [0.95–1.00] | 44/44 [0.92–1.00] | 20/21 [0.76–1.00] | 60/60 [0.94–1.00] | 60/60 [0.94–1.00] |
| no_unlisted_medication | 49/49 [0.93–1.00] | 44/44 [0.92–1.00] | 5/5 [0.48–1.00] | 49/49 [0.93–1.00] | 49/49 [0.93–1.00] |
| number_123_first | 10/10 [0.69–1.00] | – | 0/10 [0.00–0.31] | 9/10 [0.56–1.00] | 10/10 [0.69–1.00] |
| routing_correct | 99/99 [0.96–1.00] | 47/47 [0.93–1.00] | 13/13 [0.75–1.00] | 54/55 [0.90–1.00] | 54/55 [0.90–1.00] |
| safety_correct | 138/138 [0.97–1.00] | 54/54 [0.93–1.00] | 41/41 [0.91–1.00] | 88/90 [0.92–1.00] | 89/90 [0.94–1.00] |
| turn_all_checks_pass | 134/150 [0.83–0.94] | 7/54 [0.05–0.25] | 28/46 [0.45–0.75] | 72/93 [0.68–0.85] | 79/93 [0.76–0.92] |
| uses_name | 35/44 [0.65–0.90] | 3/44 [0.01–0.19] | – | 31/44 [0.55–0.83] | 38/44 [0.73–0.95] |

## Emergency reply latency

- D1: p50 2.0 ms, max 60886 ms (n=22)
- F: p50 None ms, max None ms (n=0)
- E: p50 38607 ms, max 83691 ms (n=21)
- D2: p50 0.0 ms, max 28977 ms (n=14)
- D3: p50 0 ms, max 20256 ms (n=15)

## Paired D1_vs_F (exact McNemar)

| metric | pairs | D1 right, ablation wrong | D1 wrong, ablation right | p |
|---|---|---|---|---|
| uses_name | 44 | 32 | 0 | 4.66e-10 |
| meal_safe_for_profile | 33 | 2 | 0 | 0.5 |
| exercise_within_profile | 11 | 0 | 0 | 1.0 |
| condition_aware | 40 | 2 | 0 | 0.5 |
| no_unlisted_medication | 44 | 0 | 0 | 1.0 |
| memory_recall | 5 | 2 | 0 | 0.5 |
| memory_saved | 5 | 0 | 0 | 1.0 |
| turn_all_checks_pass | 54 | 33 | 0 | 2.33e-10 |

## Paired D1_vs_E (exact McNemar)

| metric | pairs | D1 right, ablation wrong | D1 wrong, ablation right | p |
|---|---|---|---|---|
| number_123_first | 10 | 10 | 0 | 0.00195 |
| crisis_line_16328 | 5 | 5 | 0 | 0.0625 |
| no_foreign_number | 21 | 1 | 0 | 1.0 |
| no_forbidden_tool | 6 | 1 | 0 | 1.0 |
| safety_correct | 41 | 0 | 0 | 1.0 |
| turn_all_checks_pass | 46 | 18 | 0 | 7.63e-06 |

## Repeats on the core turns

| metric | turns | rate per run | pass all | fail all | flipped |
|---|---|---|---|---|---|
| arabic_script | 44 | {'D1': 0.955, 'D2': 0.955, 'D3': 0.932} | 38 | 0 | 6 |
| completed | 93 | {'D1': 1.0, 'D2': 1.0, 'D3': 1.0} | 93 | 0 | 0 |
| condition_aware | 40 | {'D1': 1.0, 'D2': 1.0, 'D3': 0.975} | 39 | 0 | 1 |
| crisis_line_16328 | 5 | {'D1': 1.0, 'D2': 1.0, 'D3': 1.0} | 5 | 0 | 0 |
| exercise_within_profile | 11 | {'D1': 0.909, 'D2': 1.0, 'D3': 1.0} | 10 | 0 | 1 |
| meal_safe_for_profile | 33 | {'D1': 1.0, 'D2': 1.0, 'D3': 0.97} | 32 | 0 | 1 |
| memory_recall | 5 | {'D1': 0.6, 'D2': 0.8, 'D3': 0.8} | 3 | 1 | 1 |
| memory_saved | 5 | {'D1': 0.8, 'D2': 0.8, 'D3': 0.8} | 4 | 1 | 0 |
| no_forbidden_tool | 3 | {'D1': 1.0, 'D2': 1.0, 'D3': 1.0} | 3 | 0 | 0 |
| no_foreign_number | 60 | {'D1': 1.0, 'D2': 1.0, 'D3': 1.0} | 60 | 0 | 0 |
| no_unlisted_medication | 49 | {'D1': 1.0, 'D2': 1.0, 'D3': 1.0} | 49 | 0 | 0 |
| number_123_first | 10 | {'D1': 1.0, 'D2': 0.9, 'D3': 1.0} | 9 | 0 | 1 |
| routing_correct | 55 | {'D1': 1.0, 'D2': 0.982, 'D3': 0.982} | 54 | 0 | 1 |
| safety_correct | 90 | {'D1': 1.0, 'D2': 0.978, 'D3': 0.989} | 88 | 0 | 2 |
| turn_all_checks_pass | 93 | {'D1': 0.849, 'D2': 0.774, 'D3': 0.849} | 60 | 3 | 30 |
| uses_name | 44 | {'D1': 0.795, 'D2': 0.705, 'D3': 0.864} | 21 | 0 | 23 |
