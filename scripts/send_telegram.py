#!/usr/bin/env python3
"""
send_telegram.py
Envia o vídeo gerado para o Telegram usando a Telegram Bot API.
Monta legenda com título, descrição visual, metadados e tags.
"""

import argparse
import html
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
import requests

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
logger = logging.getLogger("send_telegram")

BASE_DIR = Path(__file__).resolve().parent.parent


def load_settings() -> dict:
    """Carrega as configurações."""
    settings_path = BASE_DIR / "config" / "settings.json"
    with open(settings_path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_latest_video(videos_dir: Path) -> Path | None:
    """Encontra o arquivo de vídeo mais recente."""
    if not videos_dir.exists():
        return None
    videos = list(videos_dir.glob("*.mp4"))
    if not videos:
        return None
    return max(videos, key=lambda v: v.stat().st_mtime)


def find_latest_prompt(prompts_dir: Path) -> dict:
    """Encontra e lê as informações do prompt mais recente."""
    if not prompts_dir.exists():
        return {}
    prompts = list(prompts_dir.glob("prompt_*.json"))
    if not prompts:
        return {}
    latest_file = max(prompts, key=lambda p: p.stat().st_mtime)
    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def build_caption(prompt_data: dict, video_filename: str) -> str:
    """Monta a legenda formatada em HTML para o Telegram."""
    titulo = html.escape(prompt_data.get("titulo", "Novo Vídeo Gerado por IA"))
    descricao = html.escape(prompt_data.get("descricao_pt", ""))
    prompt_visual = html.escape(prompt_data.get("prompt_visual", ""))
    categoria = html.escape(prompt_data.get("categoria", "Geral"))
    
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M")

    caption_lines = [
        f"🎬 <b>{titulo}</b>",
    ]

    if descricao:
        caption_lines.append(f"\n📝 <i>{descricao}</i>")
    elif prompt_visual:
        resumo_prompt = prompt_visual[:250] + "..." if len(prompt_visual) > 250 else prompt_visual
        caption_lines.append(f"\n🔍 <i>{resumo_prompt}</i>")

    caption_lines.extend([
        f"\n📁 <b>Categoria:</b> {categoria}",
        f"⏱️ <b>Duração:</b> 12s | <b>Resolução:</b> 720p (9:16)",
        f"🤖 <b>Modelo:</b> Agnes Video 2.5 Flash / Pavo AI",
        f"📅 {timestamp}",
        f"\n#pavoai #agnesai #videoia #shorts #reels"
    ])

    full_caption = "\n".join(caption_lines)
    # Limite de legenda do Telegram é 1024 caracteres
    if len(full_caption) > 1024:
        full_caption = full_caption[:1020] + "..."

    return full_caption


def send_video(bot_token: str, chat_id: str, video_path: Path, caption: str, max_retries: int = 3) -> bool:
    """Envia o arquivo de vídeo via API do Telegram com suporte a retry."""
    file_size_mb = video_path.stat().st_size / (1024 * 1024)
    logger.info(f"Enviando {video_path.name} ({file_size_mb:.2f} MB) para o chat {chat_id}...")

    # Se menor que 50MB, envia como vídeo normal (sendVideo)
    is_normal_video = file_size_mb <= 50
    endpoint = "sendVideo" if is_normal_video else "sendDocument"
    url = f"https://api.telegram.org/bot{bot_token}/{endpoint}"

    for attempt in range(1, max_retries + 1):
        try:
            with open(video_path, "rb") as vf:
                files = {"video": vf} if is_normal_video else {"document": vf}
                data = {
                    "chat_id": chat_id,
                    "caption": caption,
                    "parse_mode": "HTML",
                    "supports_streaming": "true"
                }

                logger.info(f"[Tentativa {attempt}/{max_retries}] Fazendo upload para Telegram...")
                response = requests.post(url, data=data, files=files, timeout=180)

                if response.status_code == 200:
                    logger.info("✅ Vídeo enviado ao Telegram com sucesso!")
                    return True
                else:
                    logger.warning(f"Erro Telegram {response.status_code}: {response.text}")

        except Exception as e:
            logger.warning(f"Erro na tentativa {attempt}: {e}")

        time.sleep(5)

    return False


def main():
    parser = argparse.ArgumentParser(description="Envia vídeo para o Telegram")
    parser.add_argument("--video_path", type=str, help="Caminho do arquivo MP4", default=None)
    parser.add_argument("--prompt_file", type=str, help="Caminho do JSON com dados do prompt", default=None)
    args = parser.parse_args()

    settings = load_settings()
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.error("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não definidos no ambiente!")
        sys.exit(1)

    videos_dir = BASE_DIR / settings.get("output", {}).get("videos_dir", "output/videos")
    prompts_dir = BASE_DIR / settings.get("output", {}).get("prompts_dir", "output/prompts")

    # Localizar vídeo
    if args.video_path:
        video_path = Path(args.video_path)
    else:
        env_video = os.getenv("VIDEO_PATH")
        if env_video and os.path.exists(env_video):
            video_path = Path(env_video)
        else:
            video_path = find_latest_video(videos_dir)

    if not video_path or not video_path.exists():
        logger.error("Nenhum arquivo de vídeo encontrado para envio!")
        sys.exit(1)

    # Localizar informações do prompt
    if args.prompt_file and os.path.exists(args.prompt_file):
        with open(args.prompt_file, "r", encoding="utf-8") as f:
            prompt_data = json.load(f)
    else:
        env_prompt = os.getenv("PROMPT_PATH")
        if env_prompt and os.path.exists(env_prompt):
            with open(env_prompt, "r", encoding="utf-8") as f:
                prompt_data = json.load(f)
        else:
            prompt_data = find_latest_prompt(prompts_dir)

    caption = build_caption(prompt_data, video_path.name)
    success = send_video(bot_token, chat_id, video_path, caption)

    if not success:
        logger.error("Falha ao enviar o vídeo após todas as tentativas.")
        sys.exit(1)


if __name__ == "__main__":
    main()
