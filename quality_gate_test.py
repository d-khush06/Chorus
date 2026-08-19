import sys, json
sys.path.insert(0, '.')

from quality_gate import run_quality_gate

with open('sample_input.json', encoding='utf-8-sig') as f:
    payload = json.load(f)

result = run_quality_gate(payload)
print('=== Quality Gate on sample_input.json ===')
print('Overall Verdict    :', result['overall_verdict'])
print('Route to Human     :', result['route_to_human_review'])
print()
icons = {'PASS':'OK','WARN':'!!','FAIL':'XX','not_applicable':'--','insufficient_data':'??'}
for r in result['rule_results']:
    icon = icons.get(r['status'], '??')
    print('  [%s] [%-18s] %s: %s' % (icon, r['status'], r['rule'], r['notes'][:70]))
