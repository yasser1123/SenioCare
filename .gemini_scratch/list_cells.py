import json, sys
sys.stdout.reconfigure(encoding='utf-8')
nb = json.load(open(r'd:\PROJECTS\Graduation Project\SenioCare\Gemma4_ADK_Server (1).ipynb', encoding='utf-8'))
# Show cells 13, 15, 16, 17, 20, 22 (the important code cells)
for idx in [13, 15, 16, 17, 20, 22]:
    c = nb['cells'][idx]
    src = ''.join(c['source'])
    print(f"\n{'='*60}\nCell {idx} ({c['cell_type']}):\n{'='*60}")
    print(src[:3000])
    if len(src) > 3000:
        print(f"... (truncated, total {len(src)} chars)")
