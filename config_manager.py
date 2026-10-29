import os
import sys
import json
from pathlib import Path


class ConfigManager:
    def __init__(self, filename="config.json"):
        self.base_dir = self._get_executable_dir()
        self.config_path = os.path.join(self.base_dir, filename)
        self.temp_dir = os.path.join(self.base_dir, "temp_audio")
        self.models_dir = os.path.join(self.base_dir, "local_models")

        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.models_dir, exist_ok=True)
        self.config = self._load_or_create_default()

    def _get_executable_dir(self) -> str:
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _get_default_config(self) -> dict:
        default_docs = str(Path.home() / "Documents" / "NotasReuniones")
        return {
            "storage": {
                "output_directory": default_docs,
                "keep_audio_file": True
            },
            "stealth": {
                "hotkey_toggle_ui": "ctrl+alt+s"
            },
            "transcription_local": {
                "model_size": "base",
                "language": "es"
            },
            "ai_settings": {
                "enabled": False,
                "provider_base_url": "https://api.groq.com/openai/v1",
                "api_key": "",
                "stt_model": "whisper-large-v3-turbo",
                "llm_model": "llama-3.3-70b-versatile",
                "system_prompt": (
                    "Eres un asistente experto en análisis de reuniones. "
                    "A partir de la siguiente transcripción, genera un documento estructurado en Markdown con:\n"
                    "1. Resumen Ejecutivo.\n"
                    "2. Puntos Clave discutidos.\n"
                    "3. Acuerdos y Tareas Pendientes (Action Items).\n"
                    "4. Conclusión General."
                )
            }
        }

    def _load_or_create_default(self) -> dict:
        if not os.path.exists(self.config_path):
            default_cfg = self._get_default_config()
            self.save_config(default_cfg)
            return default_cfg

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            default_cfg = self._get_default_config()
            for key, val in default_cfg.items():
                if key not in loaded:
                    loaded[key] = val
                elif isinstance(val, dict):
                    for subkey, subval in val.items():
                        if subkey not in loaded[key]:
                            loaded[key][subkey] = subval
            return loaded
        except Exception:
            default_cfg = self._get_default_config()
            self.save_config(default_cfg)
            return default_cfg

    def save_config(self, new_config: dict = None):
        if new_config is not None:
            self.config = new_config
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)

        out_dir = self.config.get("storage", {}).get("output_directory", "")
        if out_dir:
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception:
                pass

    def get(self) -> dict:
        return self.config