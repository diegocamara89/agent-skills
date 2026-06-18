"""
call_agy.py — Chama agy (Antigravity CLI) via ConPTY para capturar saída em contextos não-TTY.

Requisito: pip install pywinpty

Uso:
    python call_agy.py "seu prompt aqui"
    python call_agy.py "seu prompt aqui" --timeout 120
    python call_agy.py "seu prompt aqui" --model gemini-3-pro-preview

Problema resolvido:
    agy -p "prompt" não produz saída quando stdout não é um TTY real (bug conhecido,
    confirmado em github.com/google-antigravity/antigravity-cli/issues/76).
    Esta solução usa pywinpty para criar um ConPTY que engana o agy.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import threading
import time
from pathlib import Path


def _find_agy() -> str:
    path = shutil.which("agy") or shutil.which("agy.exe")
    if path:
        return path
    # Fallback: localização padrão do instalador Windows
    default = Path.home() / "AppData" / "Local" / "agy" / "bin" / "agy.exe"
    if default.exists():
        return str(default)
    raise FileNotFoundError(
        "agy.exe não encontrado no PATH nem em AppData/Local/agy/bin. "
        "Instale em: https://antigravity.google/cli"
    )


def _strip_ansi(text: str) -> str:
    # OSC sequences: ESC ] ... BEL  ou  ESC ] ... ESC backslash
    text = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", text)
    # CSI sequences: ESC [ ... letra
    text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)
    # Outros ESC + caractere de controle
    text = re.sub(r"\x1b[@-Z\\-_]", "", text)
    # Carriage returns
    text = text.replace("\r", "")
    # Lixo residual de títulos de terminal sem fechamento (ex: "0;npm0;...")
    text = re.sub(r"^[^A-ZÀ-ža-zÀ-ɏ]*", "", text)
    return text


def call_agy(prompt: str, timeout: int = 120, model: str | None = None) -> str:
    """
    Executa agy -p "prompt" em um ConPTY e retorna a resposta limpa.

    Args:
        prompt: O prompt a enviar ao agy.
        timeout: Tempo máximo de espera em segundos (padrão 120).
        model: Modelo opcional (ex: "gemini-3-pro-preview").

    Returns:
        Texto de resposta com ANSI e artefatos de terminal removidos.
    """
    try:
        import winpty  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "pywinpty não instalado. Execute: pip install pywinpty"
        ) from exc

    agy_exe = _find_agy()
    cmd = [agy_exe, "-p", prompt]
    if model:
        cmd += ["--model", model]

    p = winpty.PtyProcess.spawn(cmd, dimensions=(50, 220))

    chunks: list[str] = []
    done = threading.Event()

    def _reader() -> None:
        while True:
            try:
                chunk = p.read(4096)
                if chunk:
                    chunks.append(chunk)
            except EOFError:
                break
            except Exception:
                if not p.isalive():
                    break
                time.sleep(0.05)
        done.set()

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    done.wait(timeout=timeout)

    try:
        p.close()
    except Exception:
        pass

    raw = "".join(chunks)
    clean = _strip_ansi(raw)
    lines = [ln for ln in clean.splitlines() if ln.strip()]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chama agy (Antigravity CLI) via ConPTY e imprime a resposta."
    )
    parser.add_argument("prompt", help="Prompt a enviar ao agy")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout em segundos")
    parser.add_argument("--model", default=None, help="Modelo a usar (ex: gemini-3-pro-preview)")
    args = parser.parse_args()

    result = call_agy(args.prompt, timeout=args.timeout, model=args.model)
    print(result)


if __name__ == "__main__":
    main()
