---
name: orchestrate
description: Orquestrador multi-IA para Codex, Gemini e Qwen. Cheatsheet de invocacao sem API key, gatilhos de escalada e contrato de handoff.
---

# Orchestrate — Cheatsheet para Codex e outras IAs

> Para identificacao de qual IA voce e e o fluxo canonico, consulte `SKILL.md`.
> Este arquivo contem apenas o que e exclusivo para IAs nao-Claude.

## Invocacao rapida (sem API key)

| IA | Comando seguro | Observacao critica |
|----|---------------|-------------------|
| Claude | `echo "prompt" \| claude --print` | Nao usar `-p inline` — cmd.exe corrompe `{|}%` |
| Codex | `echo "prompt" \| unset OPENAI_BASE_URL && unset OPENAI_API_KEY && codex exec --skip-git-repo-check -` | Limpar vars OpenRouter e obrigatorio |
| Qwen | `echo "prompt" \| qwen` | Le stdin nativamente |
| **agy** | `python scripts/call_agy.py "prompt"` | **NAO** usar `agy -p` direto — stdout vazio fora de TTY. Requer `pip install pywinpty` |
| Gemini | `gemini -m gemini-3-flash-preview -p "@/tmp/prompt.txt"` | **DEPRECADO** (EOL 2026-06-18) — migrar para agy |

Para prompts longos ou com `{}|%`, use sempre o script centralizado:

```bash
python scripts/run_ai_cli.py --provider claude  --prompt-file /tmp/prompt.txt
python scripts/run_ai_cli.py --provider codex   --prompt-file /tmp/prompt.txt
python scripts/run_ai_cli.py --provider qwen    --prompt-file /tmp/prompt.txt
# agy: usar call_agy.py diretamente (run_ai_cli.py nao suporta agy ainda)
python scripts/call_agy.py "prompt"
```

## Quando escalar e contrato de handoff

Consulte `SKILL.md` para: regras completas de escalada, contrato de handoff JSON e gatilho grep de risco.

Resumo: escale via `echo "..." | claude --print` quando houver alteracao multiarquivo, temas sensiveis (security/auth/pii/migration/billing), testes ausentes, ou erro apos 2 tentativas.

## Orquestracao nativa Codex (sem CLI externa)

Se voce e o Codex e quer distribuir entre sub-agentes Codex, instrua cada um com:

```json
{ "role": "executor|revisor|auditor", "task": "descricao precisa", "output_format": "json" }
```

Cada sub-agente deve responder no formato de handoff acima.
Para detalhes: `references/codex-native-multiagent.md`.
