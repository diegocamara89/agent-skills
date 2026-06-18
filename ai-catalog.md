# Quirks e Limites das IAs neste Ambiente

> Apenas comportamentos nao-obvios, bugs locais e restricoes de producao.
> Ultima atualizacao: 2026-06-18

---

## Claude Code

| Comando | Modelo default | Modelo top |
|---------|---------------|-----------|
| `echo "prompt" \| claude --print` | `claude-sonnet-4-6` | `claude-opus-4-6` |

**Stdin pipe obrigatorio** — nao usar `-p "inline"`, cmd.exe corrompe `{|}%`.

---

## Gemini

| Comando | Modelo rapido | Modelo serio |
|---------|--------------|-------------|
| `gemini -m MODELO -p "@arquivo.txt"` | `gemini-3-flash-preview` | `gemini-3-pro-preview` |

**Quirks criticos (observados em producao):**
- Rate limit 429 com 2+ chamadas simultaneas — serializar ou trocar para Codex/Qwen
- `rc=130` ("Operation cancelled") intermitente — retry ou fallback
- Stderr poluido com `[IDEClient] Failed to connect...` — nao e erro real, filtrar
- `gemini-3.1-pro-preview` retorna `ModelNotFound` neste ambiente
- **EVITAR como worker de lote** (>20 itens) — Codex processou 63 itens com 100% sucesso; Gemini falhou

---

## Codex CLI

| Comando | Variavel obrigatoria |
|---------|---------------------|
| `echo "prompt" \| codex exec --skip-git-repo-check -` | Limpar `OPENAI_BASE_URL` e `OPENAI_API_KEY` antes |

**Quirks criticos:**
- Se chamado pelo Claude (que usa OpenRouter), as vars acima contaminam a auth do Codex
- Usar flag `-` para stdin — nao passar prompt como argumento
- Estavel em lotes: 63 chamadas consecutivas sem falha (pipeline URGA, 397s)

---

## Qwen CLI

| Comando | Modo autonomo |
|---------|--------------|
| `echo "prompt" \| qwen` | `echo "prompt" \| qwen --yolo` |

- Le stdin nativamente, sem flags
- Limite: 2.000 req/dia via OpenRouter; sem limite via Ollama local

---

## Antigravity CLI (agy)

> Substituto oficial do Gemini CLI. EOL do Gemini CLI: **2026-06-18**.

| Comando | Observacao |
|---------|-----------|
| `python scripts/call_agy.py "prompt"` | **UNICO metodo confiavel em subprocesso** |
| `agy -p "prompt"` | **NAO USAR em subprocesso** — stdout vazio fora de TTY |

**Quirk critico (confirmado em producao 2026-06-18):**
- `agy -p` nao flusheia stdout quando nao ha TTY real — bug confirmado em
  [github.com/google-antigravity/antigravity-cli/issues/76](https://github.com/google-antigravity/antigravity-cli/issues/76)
- `winpty agy -p "..."` tambem falha (`stdin is not a tty`)
- **Solucao**: `scripts/call_agy.py` usa `pywinpty` para criar um ConPTY (pseudo-terminal Windows),
  enganando o agy e capturando a saida normalmente

**Instalacao do prerequisito:**
```bash
pip install pywinpty
```

**Modelo atual**: Claude Opus 4.6 (Thinking) via Google DeepMind (configuravel via `--model`).

**Timeout recomendado**: 120s padrao, 300s para tarefas complexas.

---

## Matriz de decisao rapida

| Necessidade | 1a opcao | 2a opcao |
|-------------|----------|---------|
| Analise arquitetural pontual | agy (Antigravity) | Claude |
| Bugs especificos / implementacao | Codex | Claude |
| Lote grande (>20 itens) | Codex | Qwen |
| Lote pequeno ou triagem | Qwen | agy |
| Dados sensiveis (local) | Qwen via Ollama | Claude |
| Visao executiva / plano | Claude | agy |
