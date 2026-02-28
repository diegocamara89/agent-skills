# Padroes de Equipe - Exemplificativos

> **IMPORTANTE**: Estes padroes sao EXEMPLOS, nao regras fixas.
> A IA orquestradora DEVE pensar na melhor estrutura para cada tarefa
> e DISCUTIR com o usuario antes de executar.
> O usuario pode definir sua propria estrutura a qualquer momento.

---

## PAPEIS POSSIVEIS

Cada IA pode assumir qualquer papel. Os papeis mais comuns:

| Papel | Descricao | IAs tipicas |
|-------|-----------|-------------|
| **Lider** | Define estrategia, distribui tarefas, consolida | Claude, Gemini Pro |
| **Arquiteto** | Analisa estrutura, sugere design | Gemini Pro, Claude |
| **Executor** | Implementa codigo, faz alteracoes | Codex, Qwen |
| **Revisor** | Valida qualidade, encontra problemas | Qwen, Gemini Pro |
| **Debugger** | Encontra bugs, diagnostica erros | Codex, Claude |
| **Analista** | Pesquisa, coleta dados, investiga | Gemini Flash, Qwen |
| **Documentador** | Gera relatorios, documenta decisoes | Claude, Qwen |
| **Auditor** | Valida conformidade, seguranca, privacidade | Gemini Pro, Claude |

---

## PADRAO 1: ANALISE COMPLETA DE CODIGO

```
Lider: Claude (define o que analisar)
  |
  +-- Arquiteto: Gemini Pro (anti-patterns, SOLID, design)
  |
  +-- Debugger: Codex (bugs linha por linha)
  |
  +-- Revisor: Qwen (review educativo, alternativas)
  |
  v
Consolidador: Claude (relatorio unificado)
```

**Execucao**: Arquiteto + Debugger + Revisor em PARALELO, depois Claude consolida.
**Especialidades**: Gemini (arquitetura) + Codex (bugs) + Qwen (alternativas) + Claude (sintese)

---

## PADRAO 2: DESENVOLVIMENTO AGIL

```
1. Revisor: Qwen (review inicial rapido)
2. Validador: Gemini Flash (confirma achados)
3. Se necessario: Codex ou Claude (implementacao/decisao)
```

**Execucao**: SEQUENCIAL (escala so se necessario)
**Especialidades**: Qwen (alternativas educativas) + Gemini (validacao arquitetural) + Codex/Claude (decisao final)

---

## PADRAO 3: DEBUGGING CRITICO

```
1. Debugger: Codex (identifica bug exato)
2. Analista: Qwen (entende contexto e impacto)
3. Arquiteto: Gemini Pro (verifica impacto arquitetural)
4. Lider: Claude (planeja correcao sistemica)
```

**Execucao**: SEQUENCIAL (cada etapa informa a proxima)
**Especialidades**: Codex (diagnostico) + Qwen (contexto) + Gemini (impacto arquitetural) + Claude (solucao sistemica)

---

## PADRAO 4: AUDITORIA DE PRIVACIDADE / LGPD

```
Auditor Principal: Gemini Pro (analise exaustiva)
  |
  +-- Auditor Secundario: Qwen (segunda opiniao)
  |
  v
Consolidador: Claude (relatorio final, decisao)
```

**Execucao**: Auditores em PARALELO, depois Claude decide.
**Especialidades**: Gemini (auditoria exaustiva) + Qwen (validacao independente) + Claude (decisao final)
**NOTA**: Dados devem ser anonimizados ANTES de enviar para IAs

---

## PADRAO 5: PROCESSAMENTO EM LOTE (BASICO)

```
Worker Pool:
  +-- Worker 1: Qwen (itens 1-N sequencial, rapido)
  +-- Worker 2: Gemini Flash (itens 1-N sequencial, rapido)
  |
  v
Validador: Gemini Pro ou Claude (amostragem para QA)
```

**Execucao**: Workers em PARALELO processando itens diferentes
**Especialidades**: Qwen + Gemini Flash (velocidade em processamento) + Gemini Pro/Claude (validacao de qualidade)
**NOTA**: Salvar progresso incrementalmente para nao perder trabalho
**ATENCAO**: Gemini e instavel em lotes >20 itens (ver Padrao 9 para alternativa robusta)

---

## PADRAO 6: BRAINSTORM / MULTIPLAS PERSPECTIVAS

```
Todos em PARALELO com o MESMO prompt:
  +-- Perspectiva 1: Claude (visao executiva)
  +-- Perspectiva 2: Gemini Pro (visao arquitetural)
  +-- Perspectiva 3: Qwen (visao educativa)
  |
  v
Sintese: Claude (compara, identifica consenso e divergencias)
```

**Execucao**: PARALELO total
**Especialidades**: Claude (visao estrategica) + Gemini (analise tecnica) + Qwen (alternativas praticas)

---

## PADRAO 7: PIPELINE DE VALIDACAO CRUZADA

```
Produtor: IA-A (gera resultado)
  |
  v
Validador: IA-B (valida/critica resultado)
  |
  v
Arbitro: IA-C (decide se aceita ou pede revisao)
```

**Qualquer combinacao de IAs pode assumir qualquer papel.**
**Execucao**: SEQUENCIAL (cada etapa depende da anterior)

---

## PADRAO 8: ESPECIALISTA + GENERALISTA

```
Especialista: IA mais forte na area (conforme catalogo)
  |
  v
Generalista: IA diferente para segunda opiniao
  |
  v
Decisor: Usuario ou Claude
```

---

## PADRAO 9: LOTE RESILIENTE COM CHECKPOINT

> **Baseado em caso real**: Pipeline URGA — 63 curriculos avaliados em 397s com 100% de sucesso.
> Projetado para lotes grandes (>20 itens) onde falhas parciais sao inevitaveis.

```
Preflight: Verificar executaveis (shutil.which)
  |
  v
Worker Pool (ThreadPoolExecutor, 2 workers):
  +-- Worker: Codex (principal, via stdin pipe)
  +-- Fallback: Qwen (automatico se Codex falhar)
  |
  v
Para CADA item:
  1. Chamar IA via stdin pipe
  2. Validar resposta (detector de prompt corrompido)
  3. Extrair JSON (parser balanceado)
  4. Salvar checkpoint ATOMICO (tmp → fsync → rename)
  5. Se falha: circuit breaker conta; apos 3 falhas → fallback
  |
  v
Consolidador: Claude (relatorio unificado)
```

### Componentes obrigatorios

| Componente | Funcao | Implementacao |
|------------|--------|---------------|
| **Preflight check** | Verifica CLIs antes de comecar | `shutil.which("codex")` |
| **stdin pipe** | Prompt seguro (sem corrupcao) | `codex exec --skip-git-repo-check -` |
| **Circuit breaker** | Pula modelo apos N falhas | Contador por modelo, threshold=3 |
| **Checkpoint atomico** | Retomada sem reprocessar | `.tmp` → `fsync()` → `rename()` + `.bak` |
| **Detector de invalido** | Detecta prompt corrompido | Frases como "preciso do curriculo" |
| **Parser JSON balanceado** | Extrai JSON de texto misto | Contador de `{}` respeitando strings |
| **Deduplicacao** | Evita reprocessar duplicatas | Chave composta normalizada |
| **Backoff exponencial** | Espera crescente entre retries | 5s, 15s, 45s |
| **Process tree kill** | Timeout funcional no Windows | `taskkill /F /T /PID` |

### Execucao
- Workers: 2 (equilibrio entre velocidade e rate limit)
- Timeout por item: 300s (5min)
- Retries por item: 3 (com backoff 5s/15s/45s)
- **Especialidades**: Codex (estabilidade em lote), com fallback Qwen (velocidade)

### Quando usar (em vez do Padrao 5)
- Lote >20 itens
- Itens levam >30s cada para processar
- Falhas parciais sao inaceitaveis (precisa de 100% de sucesso)
- Execucao pode ser interrompida (precisa retomar de onde parou)

---

## COMO ESCOLHER O PADRAO

Pergunte-se (e discuta com o usuario):

1. **A tarefa e simples ou complexa?**
   - Simples → 1 IA basta, nao escale
   - Complexa → Monte equipe

2. **Precisa de multiplas perspectivas ou uma so?**
   - Multiplas → Padrao 6 (brainstorm) ou 7 (validacao cruzada)
   - Uma so → Padrao 8 (especialista)

3. **Os resultados dependem um do outro?**
   - Sim → SEQUENCIAL
   - Nao → PARALELO

4. **Ha dados sensiveis?**
   - Sim → Anonimize primeiro, prefira IAs locais
   - Nao → Qualquer IA

5. **E processamento em lote?**
   - Sim, <20 itens ou tolerante a falhas → Padrao 5 (workers basico)
   - Sim, >20 itens ou precisa de 100% de sucesso → **Padrao 9 (lote resiliente)**
   - Nao → Padroes 1-4 ou 6-8

---

## CRIANDO PADROES CUSTOMIZADOS

O usuario pode definir seus proprios padroes a qualquer momento:

```
Usuario: "Quero que o Gemini analise a arquitetura, o Qwen implemente,
          e o Codex faca debug do resultado"

Orquestrador: Entendido! Montando equipe:
  1. Gemini Pro (Arquiteto) → analisa e sugere
  2. Qwen (Executor) → implementa baseado na sugestao
  3. Codex (Debugger) → valida a implementacao
  Execucao: SEQUENCIAL
  Posso prosseguir?
```
