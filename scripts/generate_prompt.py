#!/usr/bin/env python3
"""
generate_prompt.py
Gera o prompt visual do vídeo utilizando OpenRouter com fallback entre modelos gratuitos.
Suporta entrada manual de prompt ou geração criativa automática baseada no master_prompt.txt.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
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
logger = logging.getLogger("generate_prompt")

BASE_DIR = Path(__file__).resolve().parent.parent


def load_configurations():
    """Carrega as configurações do projeto, lista de modelos e prompt mestre."""
    settings_path = BASE_DIR / "config" / "settings.json"
    models_path = BASE_DIR / "config" / "models.json"
    master_prompt_path = BASE_DIR / "config" / "master_prompt.txt"

    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    with open(models_path, "r", encoding="utf-8") as f:
        models = json.load(f).get("models", [])

    with open(master_prompt_path, "r", encoding="utf-8") as f:
        master_prompt = f.read().strip()

    return settings, models, master_prompt


def extract_json_from_text(text: str) -> dict | None:
    """Extrai objeto JSON de uma resposta textual com fallback robusto."""
    text = text.strip()
    # 1. Tentar parse direto
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2. Tentar bloco de código ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    # 3. Tentar encontrar primeiro { e último }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace:last_brace + 1])
        except Exception:
            pass

    return None


def call_openrouter(api_key: str, model_id: str, prompt: str, settings: dict, max_tokens: int = 1024, temperature: float = 0.85):
    """Realiza requisição para OpenRouter API."""
    import requests

    base_url = settings.get("openrouter", {}).get("base_url", "https://openrouter.ai/api/v1")
    timeout = settings.get("openrouter", {}).get("timeout_seconds", 60)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/robsonvit/criacao-videos-pavo",
        "X-Title": "Pavo AI Video Automation"
    }

    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "Você é um gerador de prompts visuais para IA de vídeo em formato JSON estrito."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    response = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=timeout
    )

    if response.status_code == 200:
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    else:
        logger.warning(f"Erro {response.status_code} no modelo {model_id}: {response.text[:200]}")
        return None


def generate_with_fallback(api_key: str, models: list, prompt: str, settings: dict) -> tuple[dict, str]:
    """Itera sobre a lista de modelos gratuitos até obter uma resposta válida."""
    for model in models:
        model_id = model["id"]
        model_name = model.get("name", model_id)
        max_tokens = model.get("max_tokens", 1024)
        temperature = model.get("temperature", 0.8)

        logger.info(f"Tentando gerar prompt com modelo gratuito: {model_name} ({model_id})...")
        try:
            raw_content = call_openrouter(api_key, model_id, prompt, settings, max_tokens, temperature)
            if not raw_content:
                continue

            parsed_json = extract_json_from_text(raw_content)
            if parsed_json and "prompt_visual" in parsed_json:
                logger.info(f"✅ Sucesso na geração com {model_id}!")
                return parsed_json, model_id
            else:
                logger.warning(f"Resposta de {model_id} não continha JSON com prompt_visual válido. Resposta: {raw_content[:150]}")
        except Exception as e:
            logger.warning(f"Falha ao chamar modelo {model_id}: {e}")

        time.sleep(2)

    raise RuntimeError("Nenhum modelo gratuito da lista conseguiu gerar um prompt válido.")


def set_github_output(key: str, value: str):
    """Escreve saída para o arquivo GITHUB_OUTPUT se estiver executando no GitHub Actions."""
    gh_output = os.getenv("GITHUB_OUTPUT")
    if gh_output and os.path.exists(gh_output):
        with open(gh_output, "a", encoding="utf-8") as f:
            # Trata quebras de linha caso haja
            clean_value = value.replace("\r", "").replace("\n", " ")
            f.write(f"{key}={clean_value}\n")


def main():
    parser = argparse.ArgumentParser(description="Gera prompt visual para criação de vídeo Agnes/Pavo AI")
    parser.add_argument("--prompt", type=str, help="Prompt visual customizado (opcional)", default=None)
    parser.add_argument("--titulo", type=str, help="Título customizado (opcional)", default=None)
    args = parser.parse_args()

    settings, models, master_prompt = load_configurations()

    api_key = os.getenv("OPENROUTER_API_KEY")
    custom_prompt = args.prompt or os.getenv("CUSTOM_PROMPT")
    custom_titulo = args.titulo or os.getenv("CUSTOM_TITULO")

    prompts_dir = BASE_DIR / settings.get("output", {}).get("prompts_dir", "output/prompts")
    prompts_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if custom_prompt and custom_prompt.strip():
        logger.info("Usando prompt manual fornecido...")
        result = {
            "titulo": custom_titulo.strip() if custom_titulo else "Vídeo Personalizado",
            "categoria": "Custom",
            "descricao_pt": "Vídeo gerado a partir de prompt manual",
            "prompt_visual": custom_prompt.strip(),
            "_meta": {
                "model_used": "manual",
                "generated_at": datetime.now().isoformat()
            }
        }
    else:
        if not api_key:
            logger.error("OPENROUTER_API_KEY não foi encontrada nas variáveis de ambiente nem no .env!")
            sys.exit(1)

        logger.info("Iniciando geração de prompt visual via OpenRouter...")
        prompt_data, model_used = generate_with_fallback(api_key, models, master_prompt, settings)

        result = {
            "titulo": prompt_data.get("titulo", "Cena Épica 12s"),
            "categoria": prompt_data.get("categoria", "Geral"),
            "descricao_pt": prompt_data.get("descricao_pt", ""),
            "prompt_visual": prompt_data.get("prompt_visual", ""),
            "_meta": {
                "model_used": model_used,
                "generated_at": datetime.now().isoformat()
            }
        }

    output_file = prompts_dir / f"prompt_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    logger.info(f"✅ Prompt salvo em: {output_file}")
    logger.info(f"📌 Título: {result['titulo']}")
    logger.info(f"🎬 Prompt Visual: {result['prompt_visual']}")

    # Exportar saídas para GitHub Actions se aplicável
    set_github_output("prompt_path", str(output_file))
    set_github_output("prompt_title", result["titulo"])
    set_github_output("prompt_visual", result["prompt_visual"])


if __name__ == "__main__":
    main()
