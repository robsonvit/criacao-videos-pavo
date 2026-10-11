#!/usr/bin/env python3
"""
run_pipeline.py
Orquestrador local completo do pipeline de criação de vídeos:
1. Geração de roteiro/prompt via OpenRouter (modelos gratuitos)
2. Criação do vídeo via Agnes AI / Pavo AI (12s, 720p, 9:16)
3. Envio automático do vídeo para o Telegram
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

# Carregar variáveis de ambiente de .env se existir
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("pipeline")

BASE_DIR = Path(__file__).resolve().parent.parent


def run_command(command: list[str], step_name: str) -> bool:
    """Executa um comando de subprocesso com log e tratamento de erro."""
    logger.info(f"\n{'='*60}\n▶️ INICIANDO ETAPA: {step_name}\n{'='*60}")
    result = subprocess.run(command, cwd=BASE_DIR)
    if result.returncode != 0:
        logger.error(f"❌ Falha na etapa: {step_name} (código de saída: {result.returncode})")
        return False
    logger.info(f"✅ Concluída etapa: {step_name}\n")
    return True


def main():
    parser = argparse.ArgumentParser(description="Executa o pipeline completo de criação de vídeos")
    parser.add_argument("--prompt", type=str, help="Prompt visual customizado (opcional)", default=None)
    parser.add_argument("--titulo", type=str, help="Título do vídeo customizado (opcional)", default=None)
    parser.add_argument("--skip_telegram", action="store_true", help="Pular envio para Telegram")
    args = parser.parse_args()

    python_executable = sys.executable

    # 1. Gerar Prompt
    gen_cmd = [python_executable, "scripts/generate_prompt.py"]
    if args.prompt:
        gen_cmd.extend(["--prompt", args.prompt])
    if args.titulo:
        gen_cmd.extend(["--titulo", args.titulo])

    if not run_command(gen_cmd, "1. Geração do Prompt Visual (OpenRouter)"):
        sys.exit(1)

    # 2. Criar Vídeo
    video_cmd = [python_executable, "scripts/create_video.py"]
    if not run_command(video_cmd, "2. Geração do Vídeo 12s 9:16 (Agnes/Pavo AI)"):
        sys.exit(1)

    # 3. Enviar Telegram
    if not args.skip_telegram:
        tg_cmd = [python_executable, "scripts/send_telegram.py"]
        if not run_command(tg_cmd, "3. Envio do Vídeo para o Telegram"):
            sys.exit(1)
    else:
        logger.info("⏭️ Etapa de envio para Telegram pulada (--skip_telegram).")

    logger.info("🎉🎉 PIPELINE COMPLETO EXECUTADO COM SUCESSO! 🎉🎉")


if __name__ == "__main__":
    main()
