# Convencoes de Chamada - Como Chamar Cada IA via CLI

> Este documento define os comandos EXATOS para chamar cada IA.
> Testado e validado no ambiente do usuario (Windows + Git Bash/MSYS2).
> **Atualizado em 2026-02-26** com licoes aprendidas em producao (pipeline URGA).

---

## AMBIENTE DO USUARIO

- **OS**: Windows 10/11 com MSYS2/Git Bash
- **Shell padrao no Claude Code**: Bash (via MSYS2)
- **PowerShell**: Disponivel via `powershell -Command "..."`
- **Encoding**: UTF-8

---

## REGRA DE OURO: ENTREGA DO PROMPT

> **APRENDIDO EM PRODUCAO**: O metodo `-p "texto"` CORROMPE prompts no Windows.
> O `cmd.exe` interpreta `{`, `}`, `|` e `%` como operadores de shell,
> destruindo silenciosamente o conteudo enviado a IA.

| Metodo | Quando usar | Risco |
|--------|-------------|-------|
| **stdin pipe** (RECOMENDADO) | Prompts com conteudo variavel (curriculos, codigo, JSON, dados) | Nenhum |
| `-p "texto"` | Prompts curtos (< 500 chars) sem caracteres especiais | ALTO se tiver `{}|\%` |
| `@arquivo` (Gemini) | Prompts grandes pre-montados | Nenhum (requer arquivo temp) |

**Limite do cmd.exe**: 8191 caracteres maximo em argumento de linha de comando.

### stdin pipe — Padrao SEGURO para todas as IAs
```bash
# Codex: flag '-' le de stdin
echo "seu prompt" | unset OPENAI_BASE_URL && unset OPENAI_API_KEY && codex exec --skip-git-repo-check -

# Qwen: le de stdin nativamente
echo "seu prompt" | qwen

# Gemini: usar @arquivo (nao suporta stdin direto)
cat > /tmp/prompt.txt << 'EOF'
seu prompt aqui
EOF
gemini -m gemini-3-flash-preview -p "@/tmp/prompt.txt"
```

### Detector de prompt corrompido
Se a IA responder com frases como estas, o prompt chegou corrompido:
- "Preciso do curriculo", "Pode colar o conteudo", "Nao recebi"
- "Please provide", "I need the", "I don't have"

**Solucao**: Trocar de `-p` para stdin pipe e reenviar.

---

## 1. GEMINI CLI

### Chamada direta
```bash
# Prompt simples (APENAS para texto curto sem caracteres especiais)
gemini -m gemini-3-pro-preview -p "seu prompt aqui"

# Prompt de arquivo (RECOMENDADO para conteudo variavel)
gemini -m gemini-3-flash-preview -p "@caminho/do/arquivo.txt"

# Com output JSON
gemini -m gemini-3-pro-preview --output-format json -p "@/tmp/prompt.txt"
```

### Via subprocess Python — METODO POWERSHELL (RECOMENDADO no Windows)
```python
import subprocess, tempfile, os

# METODO 1 (RECOMENDADO): PowerShell com pipe nativo
# Gemini funciona MUITO melhor assim no Windows do que com @arquivo
with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
    f.write(prompt_text)
    prompt_file = f.name

output_file = tempfile.mktemp(suffix='.txt')

ps_command = f'''
$content = Get-Content -Path "{prompt_file}" -Raw
$result = $content | gemini -m gemini-3-flash-preview
$result | Out-File -FilePath "{output_file}" -Encoding utf8
'''

try:
    result = subprocess.run(
        ["powershell", "-Command", ps_command],
        capture_output=True, text=True, encoding='utf-8',
        timeout=300  # 5 minutos (Gemini precisa de timeout generoso)
    )
    with open(output_file, 'r', encoding='utf-8') as f:
        output = f.read()
finally:
    if os.path.exists(prompt_file):
        os.unlink(prompt_file)
    if os.path.exists(output_file):
        os.unlink(output_file)
```

### Via subprocess Python — METODO @ARQUIVO (fallback)
```python
import subprocess, tempfile, os

# METODO 2 (MENOS CONFIAVEL): @arquivo via Bash
# Funciona, mas pode ter problemas com timeout e rc=130
with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
    f.write(prompt_text)
    temp_path = f.name

try:
    result = subprocess.run(
        ['gemini', '-m', 'gemini-3-flash-preview', '-p', f'@{temp_path}'],
        capture_output=True, text=True, timeout=300, encoding='utf-8'
    )
    output = result.stdout
finally:
    os.unlink(temp_path)
```

### Timeout recomendado
- Flash: 120s (2min)
- Pro: 300s (5min)
- Analises longas: 600s (10min) via Bash tool com timeout

### Parsing de saida
- Saida em texto puro por padrao
- Com `--output-format json`: JSON direto
- Para extrair JSON de texto misto: usar parser balanceado (ver secao abaixo)

### ATENCAO: Instabilidade em lote
- Rate limit agressivo com 2+ chamadas simultaneas (HTTP 429)
- `rc=130` ("Operation cancelled") intermitente sem causa aparente
- Stderr poluido com `[IDEClient] Failed to connect to IDE companion extension` (filtrar)
- **Para lotes >20 itens**: preferir Codex ou Qwen como worker

---

## 2. CODEX CLI

### CRITICO: Limpar variaveis OpenRouter antes de chamar
```bash
# OBRIGATORIO quando chamado pelo Claude (que usa OpenRouter)
unset OPENAI_BASE_URL && unset OPENAI_API_KEY && codex exec --skip-git-repo-check "prompt"
```

### Chamada via stdin pipe (RECOMENDADA)
```bash
# Flag '-' le o prompt de stdin — seguro para qualquer conteudo
echo "prompt com {chaves} e |pipes|" | \
  unset OPENAI_BASE_URL && unset OPENAI_API_KEY && \
  codex exec --skip-git-repo-check -
```

### Via subprocess Python (stdin pipe)
```python
import subprocess, os

env = os.environ.copy()
env.pop('OPENAI_BASE_URL', None)
env.pop('OPENAI_API_KEY', None)

proc = subprocess.Popen(
    ['codex', 'exec', '--skip-git-repo-check', '-'],  # '-' = stdin
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, encoding='utf-8', env=env,
    creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)  # Windows
)
stdout, stderr = proc.communicate(input=prompt_text, timeout=300)
```

### Chamada direta (apenas prompts curtos sem caracteres especiais)
```bash
codex exec --skip-git-repo-check "prompt simples"

# Com sandbox de escrita
codex exec --skip-git-repo-check --sandbox workspace-write "prompt"

# Com modelo especifico
codex exec --skip-git-repo-check -m o3 "prompt"
```

### Timeout recomendado
- Padrao: 120s
- Tarefas complexas: 300s
- Maximo: 1800s (30min)

### Parsing de saida
- Saida em texto puro
- Codex tende a ser direto e conciso
- Para JSON: pedir explicitamente no prompt

### Ponto forte: Estabilidade em lote
- Testado com 63 chamadas consecutivas sem falha (pipeline URGA)
- stdin pipe funciona de forma confiavel com qualquer conteudo
- 1 chamada combinada pode substituir 2 chamadas Gemini (analise + validacao)

---

## 3. QWEN CLI

### Chamada via stdin pipe (RECOMENDADA)
```bash
# stdin pipe — seguro para qualquer conteudo
echo "prompt com {chaves} e |pipes|" | qwen
```

### Chamada direta (apenas prompts curtos)
```bash
# Prompt simples
qwen -p "prompt"

# Modo autonomo (executa codigo)
qwen -p "prompt" --yolo
```

### Via arquivo temporario (Windows - para prompts grandes)
```bash
# Escrever prompt em arquivo temp, depois pipe
cat > /tmp/qwen_prompt.txt << 'PROMPT_EOF'
prompt grande aqui
PROMPT_EOF
cat /tmp/qwen_prompt.txt | qwen && rm /tmp/qwen_prompt.txt
```

### Timeout recomendado
- Padrao: 60s
- Tarefas maiores: 120s

### Parsing de saida
- Saida em texto puro com formatacao Markdown
- Qwen e mais verboso - pode precisar de limpeza
- Para JSON: pedir "Responda APENAS JSON, sem texto adicional"

### Limites
- 2.000 requisicoes/dia (gratuito via OpenRouter)
- Sem limite via Ollama local

---

## 4. CLAUDE CODE (auto-referencia)

### Chamada direta (de outro processo)
```bash
claude -p "prompt"
```

### NOTA: Claude normalmente e o ORQUESTRADOR, nao o orquestrado.
Raramente voce chamara Claude de dentro do Claude.
Mas e possivel para pipelines encadeados.

---

## PADROES DE CHAMADA COMUNS

### Padrao 1: Chamada simples com captura
```bash
# Bash tool - resultado vai para stdout
resultado=$(gemini -m gemini-3-flash-preview -p "analise X")
echo "$resultado"
```

### Padrao 2: Encadeamento (output de uma IA como input de outra)
```bash
# Gemini analisa, Qwen valida
analise=$(gemini -m gemini-3-pro-preview -p "analise arquitetural de X")
validacao=$(echo "$analise" | qwen -p "valide esta analise: ")
```

### Padrao 3: Paralelo via background
```bash
# Rodar em paralelo e coletar resultados
gemini -m gemini-3-flash-preview -p "tarefa A" > /tmp/resultado_gemini.txt &
qwen -p "tarefa B" > /tmp/resultado_qwen.txt &
wait
# Ler resultados
cat /tmp/resultado_gemini.txt
cat /tmp/resultado_qwen.txt
```

### Padrao 4: Com arquivo de prompt (para prompts grandes)
```bash
# Salvar prompt em arquivo
cat > /tmp/prompt.txt << 'PROMPT_EOF'
Seu prompt grande aqui
com multiplas linhas
PROMPT_EOF

# Chamar com @arquivo
gemini -m gemini-3-pro-preview -p "@/tmp/prompt.txt"
```

### Padrao 5: Resultado em arquivo (para saidas grandes)
```bash
gemini -m gemini-3-pro-preview -p "prompt" > resultado.txt 2>&1
```

---

## WINDOWS: KILL DE ARVORE DE PROCESSO

> **APRENDIDO EM PRODUCAO**: `subprocess.run(timeout=N)` NAO mata processos filhos no Windows.
> O `cmd.exe` cria uma arvore de processos — timeout so mata o pai, filhos continuam rodando.
> Resultado: timeout de 120s pode levar 279s+ ate retornar.

### Solucao obrigatoria para scripts Python no Windows

```python
import subprocess, os

_CREATE_NEW_PROCESS_GROUP = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)

def _kill_process_tree(proc):
    """Mata o processo E todos os seus filhos no Windows."""
    try:
        if os.name == 'nt':
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                capture_output=True, timeout=10
            )
        else:
            proc.kill()
        proc.wait(timeout=5)
    except Exception:
        pass

# Uso:
proc = subprocess.Popen(
    cmd,
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, encoding='utf-8',
    creationflags=_CREATE_NEW_PROCESS_GROUP  # OBRIGATORIO no Windows
)
try:
    stdout, stderr = proc.communicate(input=prompt, timeout=300)
except subprocess.TimeoutExpired:
    _kill_process_tree(proc)  # Mata TODA a arvore
    raise
```

### Regras
1. SEMPRE criar processo com `CREATE_NEW_PROCESS_GROUP`
2. Em caso de timeout, usar `taskkill /F /T /PID <pid>` (nao `proc.kill()`)
3. Depois: `proc.wait(timeout=5)` para limpar

---

## FILTRO DE STDERR (IDEClient e outros ruidos)

O Gemini CLI emite mensagens inofensivas no stderr que parecem erros:
```
[IDEClient] Failed to connect to IDE companion extension
```

**NAO trate stderr como indicador de falha.** Filtre ruido conhecido:
```python
_STDERR_NOISE = ["IDEClient", "cached credentials", "ide install",
                 "companion extension", "mcp:", "thinking"]

def _filter_stderr(stderr_raw):
    if not stderr_raw:
        return ""
    lines = [l for l in stderr_raw.strip().splitlines()
             if not any(w in l for w in _STDERR_NOISE)]
    return " | ".join(lines)[:200]
```

---

## TRATAMENTO DE ERROS

### Erros comuns e solucoes

| Erro | IA | Solucao |
|------|-----|---------|
| Timeout | Todas | Aumentar timeout, reduzir prompt |
| Prompt corrompido | Todas | Trocar `-p` por stdin pipe |
| "command not found" | Todas | Verificar PATH, reinstalar |
| JSON invalido | Todas | Parser balanceado (ver abaixo) |
| Rate limit (429) | Gemini | Serializar chamadas, usar Codex/Qwen |
| rc=130 "Operation cancelled" | Gemini | Retry ou trocar para Codex |
| Auth error | Codex | Limpar OPENAI_BASE_URL/KEY |
| Encoding | Todas | Forcar UTF-8 no subprocess |
| Resposta invalida | Todas | Detectar frases de "nao recebi" (ver Regra de Ouro) |
| Processo zombie (Windows) | Todas | `taskkill /F /T /PID` (ver secao acima) |

### Extracao de JSON — Parser balanceado (3 niveis)

> **APRENDIDO EM PRODUCAO**: `grep -oP '\{.*\}'` e GULOSO — casa do primeiro `{`
> ao ultimo `}` do texto inteiro, englobando lixo. Usar parser balanceado.

```python
import json, re

def _extrair_json_balanceado(texto):
    """Encontra o primeiro JSON valido com chaves balanceadas."""
    inicio = texto.find('{')
    while inicio != -1:
        depth = 0
        in_string = False
        escape_next = False
        for i in range(inicio, len(texto)):
            c = texto[i]
            if escape_next:
                escape_next = False
                continue
            if c == '\\' and in_string:
                escape_next = True
                continue
            if c == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    candidato = texto[inicio:i + 1]
                    try:
                        return json.loads(candidato)
                    except (json.JSONDecodeError, TypeError):
                        break
        inicio = texto.find('{', inicio + 1)
    return None

def extrair_json(texto):
    """Extrai JSON de saida de IA com 3 niveis de fallback."""
    if not texto:
        return None
    # Nivel 1: texto inteiro e JSON puro
    try:
        return json.loads(texto)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    # Nivel 2: JSON dentro de bloco markdown ```json ... ```
    m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', texto)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, TypeError):
            pass
    # Nivel 3: parser balanceado (mais robusto)
    return _extrair_json_balanceado(texto)
```

### Funcao de validacao JSON (Bash — uso rapido)
```bash
validar_json() {
    local json="$1"
    if echo "$json" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
        return 0
    fi
    # fallback: extrair via Python com parser balanceado
    local extraido
    extraido=$(echo "$json" | python3 -c "
import sys, json, re
txt = sys.stdin.read()
m = re.search(r'\`\`\`(?:json)?\s*(\{[\s\S]*?\})\s*\`\`\`', txt)
if m:
    try:
        json.loads(m.group(1)); print(m.group(1)); exit(0)
    except: pass
# fallback simples
start = txt.find('{')
end = txt.rfind('}')
if start >= 0 and end > start:
    candidate = txt[start:end+1]
    try:
        json.loads(candidate); print(candidate); exit(0)
    except: pass
exit(1)
" 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$extraido" ]; then
        echo "$extraido"
        return 0
    fi
    return 1
}
```

### Retry logic com backoff exponencial
```bash
# Tentar ate 3 vezes com backoff crescente (5s, 15s, 45s)
for i in 1 2 3; do
    resultado=$(gemini -m gemini-3-flash-preview -p "@/tmp/prompt.txt" 2>&1) && break
    echo "Tentativa $i falhou, aguardando $((5 * 3 ** ($i - 1)))s..."
    sleep $((5 * 3 ** ($i - 1)))
done
```

---

## DICAS DE PERFORMANCE

1. **Use stdin pipe** para qualquer prompt com conteudo variavel
2. **Prefira Codex ou Qwen** para lotes grandes (Gemini e instavel em lote)
3. **Reserve Gemini Pro** para analises pontuais de arquitetura
4. **Salve resultados intermediarios** com escrita atomica (tmp → fsync → rename)
5. **Use `shutil.which()`** para resolver executaveis em vez de hardcoded `.cmd`
6. **Filtre stderr** antes de tratar como erro (IDEClient, etc.)
7. **Nao use `except:` bare** — capture excecoes especificas (impede Ctrl+C)
