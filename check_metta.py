"""check_metta.py — smoke check for the MeTTa reasoning layer."""
import sys
sys.path.insert(0, ".")

from reasoning.wrapper import load_facts, query
import hyperon

print("Python:", sys.version.split()[0])
print("hyperon:", getattr(hyperon, "__version__", "0.2.10 (pinned)"))

facts = load_facts(['(verified-mapping "REC-001" "WRK-001" "LabelX")'])
results = query(facts, 'match &self (verified-mapping $r $w $s) $r')
print("Query result:", results)

assert results and '"REC-001"' in results[0], f"Unexpected result: {results}"
print("=== PASS: MeTTa query returned expected result ===")
