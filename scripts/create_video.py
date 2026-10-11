#!/usr/bin/env python3
"""
create_video.py
Envia solicitação de geração de vídeo para a API Agnes AI / Pavo AI (agnes-video-2.5-flash).
Executa polling do status da renderização até conclusão e baixa o vídeo MP4 final.
Inclui tratamento automático de fila cheia (503) e rate limit (429 - 1 a cada 2 minutos).
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
import urllib.request
import urllib.error

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
logger = logging.getLogger("create_video")

BASE_DIR = Path(__file__).resolve().parent.parent


def load_settings() -> dict:
    """Carrega as configurações do projeto."""
    settings_path = BASE_DIR / "config" / "settings.json"
    with open(settings_path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_latest_prompt_file(prompts_dir: Path) -> Path | None:
    """Encontra o arquivo de prompt mais recente no diretório."""
    if not prompts_dir.exists():
        return None
    prompt_files = list(prompts_dir.glob("prompt_*.json"))
    if not prompt_files:
        return None
    return max(prompt_files, key=lambda p: p.stat().st_mtime)


def submit_video_request(api_key: str, base_url: str, prompt_text: str, settings: dict) -> str:
    """
    Envia a requisição POST para criação do vídeo.
    Trata erros de fila cheia (503) e rate limit (429) com tentativas automáticas.
    """
    create_url = f"{base_url.rstrip('/')}/videos"
    video_cfg = settings.get("video", {})
    api_cfg = settings.get("api", {})

    payload = {
        "model": video_cfg.get("model", "agnes-video-2.5-flash"),
        "mode": video_cfg.get("mode", "text"),
        "prompt": prompt_text,
        "size": video_cfg.get("size", "720P"),
        "aspect_ratio": video_cfg.get("aspect_ratio", "9:16"),
        "seconds": str(video_cfg.get("seconds", "12")),
        "n": video_cfg.get("n", 1)
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "PavoAI-Automation/1.0"
    }

    max_retries = api_cfg.get("max_retries", 12)
    retry_delay = api_cfg.get("retry_delay_seconds", 30)

    logger.info(f"Enviando solicitação de vídeo para {create_url}...")
    logger.info(f"Parâmetros: Modelo={payload['model']}, Duração={payload['seconds']}s, Resolução={payload['size']}, Formato={payload['aspect_ratio']}")

    data_bytes = json.dumps(payload).encode("utf-8")

    for attempt in range(1, max_retries + 1):
        req = urllib.request.Request(create_url, data=data_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                resp_text = response.read().decode("utf-8")
                res_json = json.loads(resp_text)
                video_id = res_json.get("video_id") or res_json.get("id") or res_json.get("task_id")
                if video_id:
                    logger.info(f"✅ Vídeo colocado na fila com sucesso! ID da Tarefa: {video_id}")
                    return video_id
                else:
                    logger.warning(f"Resposta sem video_id: {resp_text}")
                    return resp_text

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            logger.warning(f"[Tentativa {attempt}/{max_retries}] Erro HTTP {e.code}: {err_body}")

            # 503 Fila cheia ou 429 Limite de taxa (1 RPM no plano gratuito)
            if e.code in (503, 429) or "queue_full" in err_body or "rate_limit" in err_body:
                motivo = "Rate Limit de 1 RPM" if (e.code == 429 or "rate_limit" in err_body) else "Fila da GPU Agnes AI cheia"
                logger.info(f"⏳ {motivo}. Respeitando janela de segurança: aguardando {retry_delay}s antes da tentativa {attempt + 1}/{max_retries}...")
                time.sleep(retry_delay)
                continue
            else:
                raise RuntimeError(f"Erro ao solicitar vídeo: HTTP {e.code} - {err_body}")

        except Exception as ex:
            logger.warning(f"[Tentativa {attempt}/{max_retries}] Erro de conexão: {ex}")
            time.sleep(10)

    raise TimeoutError("Número máximo de tentativas de submissão atingido sem sucesso.")


def poll_video_status(api_key: str, base_url: str, video_id: str, settings: dict) -> str:
    """
    Consulta periodicamente o status da tarefa até completion ou timeout.
    Retorna a URL do vídeo pronto.
    """
    api_cfg = settings.get("api", {})
    poll_interval = api_cfg.get("polling_interval_seconds", 15)
    timeout_sec = api_cfg.get("timeout_seconds", 600)
    model_name = api_cfg.get("model_name_poll", "agnes-video-2.5-flash")

    # URLs possíveis para polling
    primary_url = f"{base_url.rstrip('/')}/agnesapi?video_id={video_id}&model_name={model_name}"
    fallback_url = f"{base_url.rstrip('/')}/videos/{video_id}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "PavoAI-Automation/1.0"
    }

    start_time = time.time()
    logger.info(f"Iniciando monitoramento da renderização do vídeo (ID: {video_id})...")

    while time.time() - start_time < timeout_sec:
        elapsed = int(time.time() - start_time)
        # Tenta URL primária (/v1/agnesapi), se der 404 tenta fallback (/v1/videos/{id})
        data = None
        for test_url in [primary_url, fallback_url]:
            req = urllib.request.Request(test_url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    resp_text = resp.read().decode("utf-8")
                    data = json.loads(resp_text)
                    break
            except urllib.error.HTTPError as e:
                if e.code == 404 and test_url == primary_url:
                    continue  # tenta fallback
                logger.warning(f"Erro HTTP {e.code} ao consultar status: {e.read().decode('utf-8')[:150]}")
            except Exception as e:
                logger.warning(f"Erro na requisição de polling: {e}")

        if data:
            status = data.get("status", "").lower()
            logger.info(f"[{elapsed}s decorridos] Status: {status}")

            if status == "completed":
                # Encontrar a URL do vídeo
                video_url = data.get("url") or data.get("video_url")
                if not video_url and "data" in data and isinstance(data["data"], dict):
                    video_url = data["data"].get("url") or data["data"].get("video_url")

                if video_url:
                    logger.info(f"🎉 Renderização concluída com sucesso! URL: {video_url}")
                    return video_url
                else:
                    logger.error(f"Status completed mas sem URL encontrada no payload: {data}")
                    raise ValueError("URL do vídeo ausente na resposta de sucesso.")

            elif status in ("failed", "error"):
                error_msg = data.get("error") or data.get("message") or "Erro desconhecido na geração"
                logger.error(f"❌ Renderização falhou: {error_msg}")
                raise RuntimeError(f"Renderização de vídeo falhou: {error_msg}")

            # Se status for queued ou processing, continua aguardando
        time.sleep(poll_interval)

    raise TimeoutError(f"Tempo limite excedido ({timeout_sec}s) aguardando renderização do vídeo.")


def download_video(video_url: str, output_path: Path):
    """Faz o download do arquivo de vídeo a partir da URL pública."""
    logger.info(f"Baixando vídeo para {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = {"User-Agent": "PavoAI-Automation/1.0"}
    req = urllib.request.Request(video_url, headers=headers)

    with urllib.request.urlopen(req, timeout=60) as resp:
        with open(output_path, "wb") as f_out:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f_out.write(chunk)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    logger.info(f"✅ Download concluído! Arquivo: {output_path.name} ({size_mb:.2f} MB)")


def set_github_output(key: str, value: str):
    """Escreve saída para o arquivo GITHUB_OUTPUT se estiver executando no GitHub Actions."""
    gh_output = os.getenv("GITHUB_OUTPUT")
    if gh_output and os.path.exists(gh_output):
        with open(gh_output, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


def main():
    parser = argparse.ArgumentParser(description="Gera vídeo usando Agnes AI / Pavo AI")
    parser.add_argument("--prompt_file", type=str, help="Caminho do arquivo JSON do prompt", default=None)
    parser.add_argument("--prompt", type=str, help="Prompt de vídeo direto via CLI", default=None)
    args = parser.parse_args()

    settings = load_settings()
    api_key = os.getenv("AGNES_API_KEY")
    raw_base = os.getenv("AGNES_BASE_URL")
    base_url = raw_base.strip() if raw_base and raw_base.strip() else settings.get("api", {}).get("base_url", "https://apihub.agnes-ai.com/v1")

    if not api_key:
        logger.error("AGNES_API_KEY não configurada no ambiente nem no .env!")
        sys.exit(1)

    prompts_dir = BASE_DIR / settings.get("output", {}).get("prompts_dir", "output/prompts")
    videos_dir = BASE_DIR / settings.get("output", {}).get("videos_dir", "output/videos")
    videos_dir.mkdir(parents=True, exist_ok=True)

    prompt_text = None
    prompt_file = None

    if args.prompt and args.prompt.strip():
        prompt_text = args.prompt.strip()
    elif args.prompt_file:
        prompt_file = Path(args.prompt_file)
    else:
        # Tenta pegar da variável de ambiente ou procurar o arquivo mais recente
        env_prompt_path = os.getenv("PROMPT_PATH")
        if env_prompt_path and os.path.exists(env_prompt_path):
            prompt_file = Path(env_prompt_path)
        else:
            prompt_file = find_latest_prompt_file(prompts_dir)

    if prompt_file and prompt_file.exists():
        logger.info(f"Lendo prompt do arquivo: {prompt_file}")
        with open(prompt_file, "r", encoding="utf-8") as f:
            p_data = json.load(f)
            prompt_text = p_data.get("prompt_visual") or p_data.get("prompt")
    elif not prompt_text:
        # Fallback se nenhum prompt foi fornecido
        prompt_text = os.getenv("CUSTOM_PROMPT")

    if not prompt_text:
        logger.error("Nenhum prompt visual disponível para criar o vídeo!")
        sys.exit(1)

    logger.info(f"🎬 Prompt para geração: {prompt_text}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    video_filename = f"video_{timestamp}.mp4"
    output_video_path = videos_dir / video_filename

    # 1. Enviar solicitação de criação
    video_id = submit_video_request(api_key, base_url, prompt_text, settings)

    # 2. Polling até conclusão
    video_url = poll_video_status(api_key, base_url, video_id, settings)

    # 3. Baixar arquivo MP4
    download_video(video_url, output_video_path)

    # 4. Salvar metadados da execução
    meta_path = videos_dir / f"meta_{timestamp}.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "video_id": video_id,
            "video_url": video_url,
            "local_path": str(output_video_path),
            "prompt": prompt_text,
            "created_at": datetime.now().isoformat()
        }, f, indent=2, ensure_ascii=False)

    # 5. Exportar outputs para GitHub Actions
    set_github_output("video_path", str(output_video_path))
    set_github_output("video_id", video_id)
    set_github_output("video_url", video_url)

    logger.info("🏁 Processo de criação de vídeo concluído com sucesso!")


if __name__ == "__main__":
    main()
