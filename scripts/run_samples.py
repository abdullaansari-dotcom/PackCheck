"""Run the sample labels through the rules engine and write samples/sample_results.json.
Usage: python -m scripts.run_samples"""
import json

from app import config
from app.engine import analyze_text

out = []
for s in json.loads(config.SAMPLES_FILE.read_text(encoding="utf-8")):
    r = analyze_text(s["text"], s["category"], s["pack_type"])
    out.append({"name": s["name"], "request": {k: s[k] for k in ("text", "category", "pack_type")},
                "response": r.model_dump(mode="json")})
    print(f'{s["name"]:40s} {r.verdict:14s} {r.summary}')
(config.BASE_DIR / "samples" / "sample_results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print("wrote samples/sample_results.json")
