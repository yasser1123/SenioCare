import json, sys
sys.stdout.reconfigure(encoding='utf-8')
nb = json.load(open(r'd:\PROJECTS\Graduation Project\SenioCare\Gemma4_ADK_Server (1).ipynb', encoding='utf-8'))
# Show cells 8, 10 (model config)
for idx in [8, 10]:
    c = nb['cells'][idx]
    src = ''.join(c['source'])
    print(f"\n{'='*60}\nCell {idx}:\n{'='*60}")
    print(src[:2000])
