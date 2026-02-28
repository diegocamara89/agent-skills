# Catalogo de IAs Disponiveis

> **Ultima atualizacao**: 2026-02-26
> **Como atualizar**: Edite este arquivo quando novos modelos forem lancados.
> Para verificar modelos atuais: `gemini --help`, `codex --help`, `qwen --help`, `claude --version`

---

## 1. CLAUDE CODE

| Campo | Valor |
|-------|-------|
| **Comando** | `claude -p "prompt"` |
| **Modelo Top** | `claude-opus-4-6` |
| **Modelo Rapido** | `claude-haiku-4-5-20251001` |
| **Modelo Default** | `claude-sonnet-4-5-20250929` |
| **Velocidade** | Medio a detalhado (depende do modelo) |
| **Contexto** | 1M tokens (beta) |
| **Timeout** | Configuravel ate 60min |
| **Saida max** | 128K tokens |

### Forcas
- Orquestracao e visao executiva (10/10)
- Planejamento estrategico e roadmaps
- Subagents nativos (Explore, Plan, general-purpose)
- Agent Teams (paralelismo real, experimental)

### Fraquezas
- Mais lento que modelos especializados em tarefas pontuais
- Overhead desnecessario para tarefas triviais

### Quando usar como membro da equipe
- Lider/Orquestrador (papel natural)
- Consolidador de resultados de outras IAs
- Analista de riscos sistemicos
- Documentador final

---

## 2. GEMINI

| Campo | Valor |
|-------|-------|
| **Comando** | `gemini -m MODELO -p "prompt"` |
| **Modelo Top** | `gemini-3-pro-preview` |
| **Modelo Rapido** | `gemini-3-flash-preview` |
| **Velocidade** | Rapido (Flash ~2min) / Medio (Pro ~5min) |
| **Contexto** | 1M tokens |
| **Timeout** | Configuravel via Bash (ate 10min) |
| **Output format** | Suporta `--output-format json` |

### Forcas
- Arquitetura e design patterns (9.5/10)
- Anti-patterns, SOLID, code smells
- Analise rapida (~2min)
- GRATUITO

### Fraquezas
- Pode ser verboso demais
- Menos preciso em debugging linha-a-linha
- **Rate limit agressivo** com 2+ chamadas simultaneas (HTTP 429) — observado em producao
- **rc=130 intermitente** ("Operation cancelled") sem causa aparente
- **Instavel em lotes grandes** (>20 chamadas consecutivas): timeouts aleatorios, falhas silenciosas
- **Stderr poluido** com `[IDEClient] Failed to connect...` — causa falsos positivos se nao filtrado

### Quando usar como membro da equipe
- Arquiteto (analise estrutural) — **analises pontuais, nao em lote**
- Revisor de qualidade
- Validador de decisoes tecnicas
- Analista de performance
- **EVITAR como worker de lote** — preferir Codex ou Qwen para processamento em massa

### Modelos disponiveis (verificar com `gemini /model`)
- `gemini-3-pro-preview` - Analises serias, arquitetura, decisoes
- `gemini-3-flash-preview` - Rapido, bom custo-beneficio

---

## 3. CODEX CLI

| Campo | Valor |
|-------|-------|
| **Comando** | `codex exec --skip-git-repo-check "prompt"` |
| **Modelo Top** | `gpt-5.3-codex` |
| **Modelo Rapido** | `gpt-5.3-codex-spark` |
| **Velocidade** | Medio (120s-300s tipico) |
| **Timeout** | 30min configuravel |

### IMPORTANTE: Variaveis de ambiente
Quando chamado pelo Claude, DEVE limpar variaveis OpenRouter:
```bash
# Bash
unset OPENAI_BASE_URL && unset OPENAI_API_KEY && codex exec --skip-git-repo-check "prompt"
```

### IMPORTANTE: stdin pipe (flag `-`)
Para prompts com conteudo variavel (curriculos, codigo, JSON), usar stdin:
```bash
echo "prompt" | codex exec --skip-git-repo-check -
```

### Forcas
- Debugging linha-a-linha (9.5/10)
- Precisao cirurgica em bugs
- Implementacao de codigo
- **Estavel em lotes grandes** — testado com 63 chamadas consecutivas sem falha (pipeline URGA)
- **stdin pipe confiavel** — sem corrupcao de prompt com `{`, `|`, `%`
- **1 chamada combinada** pode substituir 2 chamadas Gemini (analise + validacao)

### Fraquezas
- Problemas com arquivos muito grandes
- Responde melhor a prompts especificos (menos exploratório que Gemini)

### Quando usar como membro da equipe
- Debugger (encontrar bugs exatos)
- Implementador (escrever codigo)
- Executor de tarefas especificas
- **Worker de lote** (alternativa estavel ao Gemini para processamento em massa)

---

## 4. QWEN CLI

| Campo | Valor |
|-------|-------|
| **Comando** | `qwen -p "prompt"` |
| **Modo autonomo** | `qwen -p "prompt" --yolo` |
| **Modelo** | `qwen3-coder` (via OpenRouter: `qwen/qwen3-coder:free`) |
| **Modelo Local** | `qwen3-coder-next` (80B/3B ativo, via Ollama) |
| **Velocidade** | Rapido (60-120s tipico) |
| **Contexto** | 256K tokens |

### Forcas
- Code review educativo (8.5/10)
- Multiplas implementacoes alternativas
- GRATUITO
- Pode orquestrar Codex CLI

### Fraquezas
- Ferramentas internas limitadas
- Menos preciso que Gemini Pro em arquitetura

### Quando usar como membro da equipe
- Professor/Explicador (analise educativa)
- Revisor inicial (primeiro olhar gratuito)
- Normalizador de dados (tarefas repetitivas)
- Worker para tarefas em lote (gratuito)

---

## 5. OUTRAS IAs CLI (FUTURAS)

Adicione aqui novas IAs conforme forem instaladas:

| IA | Comando | Modelo | Status |
|----|---------|--------|--------|
| *Exemplo* | `nova-ia -p "prompt"` | `modelo-x` | Nao instalada |

---

## MATRIZ DE DECISAO RAPIDA

| Necessidade | 1a Opcao | 2a Opcao | Justificativa |
|-------------|----------|----------|---------------|
| Analise rapida | Qwen | Gemini Flash | Velocidade |
| Arquitetura (pontual) | Gemini Pro | Claude | Profundidade estrutural |
| Bugs especificos | Codex | Claude | Precisao cirurgica |
| Visao executiva | Claude | Gemini Pro | Estrategia e roadmaps |
| **Lote grande (>20 itens)** | **Codex** | **Qwen** | **Estabilidade em batch** |
| Lote pequeno (1-20 itens) | Qwen | Gemini Flash | Velocidade + fallback |
| Dados sensiveis | Qwen Local (Ollama) | Claude | Privacidade local |
| Code review educativo | Qwen | Gemini Pro | Multiplas alternativas |
| Analise de gargalos | Gemini Pro | Claude | Performance deep-dive |

> **NOTA (2026-02-26)**: A recomendacao de Gemini para lotes grandes foi rebaixada apos
> falhas sistematicas em producao (rate limit 429, rc=130, timeouts aleatorios com 63 candidatos).
> Codex processou o mesmo lote com 100% de sucesso em 397s.
