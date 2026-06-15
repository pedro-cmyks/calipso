#!/usr/bin/env python3
"""
test_learning.py — El bucle de aprendizaje ajusta pesos desde la telemetría,
y los overrides por repo se aplican (defaults -> global -> proyecto).
"""
import json
import os
import pathlib
import tempfile

_HOME = tempfile.mkdtemp(prefix="calipso_learn_")
os.environ["CALIPSO_HOME"] = _HOME

from calipso import telemetry, learning, capabilities  # noqa: E402


def _turn(task_type, model_id, failed, latency):
    telemetry.log_event(
        "chat_turn", task_type=task_type, model_id=model_id,
        fallbacks=([{"to": "local"}] if failed else []), latency_ms=latency)


def main() -> int:
    fails = []

    def check(name, cond):
        print(f"  [{'OK' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    # --- 1) aprendizaje global (a nivel de MODELO) ---
    # analysis: codex gana (sin fallos), opus pierde (falla siempre)
    for _ in range(4):
        _turn("analysis", "subscription:codex", False, 5000)
        _turn("analysis", "subscription:claude:opus", True, 9000)
    # reasoning: deepseek gana, local-7b pierde
    for _ in range(4):
        _turn("reasoning", "api:deepseek-chat", False, 4000)
        _turn("reasoning", "local:qwen2.5:7b", True, 30000)

    result = learning.learn()
    print("  aprendido:", json.dumps(result["changed"], ensure_ascii=False))

    backends = capabilities.load_backends()
    codex_an = backends["subscription:codex"]["strengths"].get("analysis")
    opus_an = backends["subscription:claude:opus"]["strengths"].get("analysis")
    api_re = backends["api:deepseek-chat"]["strengths"].get("reasoning")

    check("codex.analysis subio (0.8 -> ~0.85)", codex_an and codex_an > 0.8)
    check("opus.analysis bajo (0.97 -> ~0.92)", opus_an and opus_an < 0.97)
    check("deepseek.reasoning subio (0.9 -> ~0.95)", api_re and api_re > 0.9)
    check("persistio en ~/.calipso/capabilities.json",
          capabilities.CAP_FILE.exists())

    # --- 2) override por repo (defaults -> global -> proyecto) ---
    proj = pathlib.Path(tempfile.mkdtemp(prefix="calipso_repo_"))
    (proj / ".calipso").mkdir(parents=True, exist_ok=True)
    (proj / ".calipso" / "capabilities.json").write_text(json.dumps(
        {"backends": {"subscription:codex": {"strengths": {"repo": 0.5}}}}),
        encoding="utf-8")
    merged = capabilities.load_backends(project_root=str(proj))
    check("override de repo aplica (codex.repo = 0.5)",
          merged["subscription:codex"]["strengths"]["repo"] == 0.5)
    check("lo no-override queda default (codex.code = 1.0)",
          merged["subscription:codex"]["strengths"]["code"] == 1.0)

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: aprendizaje global + override por repo funcionando")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
