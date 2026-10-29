import os
import sys
import shutil
import warnings
import logging
import subprocess
import traceback

# 1. Variables de entorno críticas
os.environ["HF_HUB_DISABLE_XET"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "4"

warnings.filterwarnings("ignore")

# 2. PARCHE CRÍTICO PARA PYINSTALLER (console=False) EN WINDOWS:
# En Windows, cuando un .exe se compila con console=False, cualquier llamada a subprocess.Popen
# (como la que hace SpeechRecognition al llamar a flac-win32.exe) crashea o se congela
# porque stdin/stdout/stderr del proceso padre son inválidos o abre una ventana fantasma.
if sys.platform == "win32":
    _original_popen = subprocess.Popen

    class _SafeWindowlessPopen(_original_popen):
        def __init__(self, *args, **kwargs):
            if "startupinfo" not in kwargs or kwargs["startupinfo"] is None:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE
                kwargs["startupinfo"] = si
            if "creationflags" not in kwargs:
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            if "stdin" not in kwargs or kwargs["stdin"] is None:
                kwargs["stdin"] = subprocess.DEVNULL
            super().__init__(*args, **kwargs)

    subprocess.Popen = _SafeWindowlessPopen

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from datetime import datetime


def log_console(msg: str):
    """Guarda el log siempre en un archivo físico junto al .exe y en consola si existe."""
    try:
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        log_path = os.path.join(base_dir, "syncaudio_debug.log")
        timestamp = datetime.now().strftime("%H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(f"[{timestamp}] {msg}\n")
        if sys.stdout is not None and hasattr(sys.stdout, "write"):
            print(msg, flush=True)
    except Exception:
        pass


class AIProcessor:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self._ensure_flac_outside_temp()

    def _ensure_flac_outside_temp(self):
        """
        Cuando corre como .exe en PyInstaller, copia flac-win32.exe fuera de %TEMP%
        hacia la carpeta local de trabajo para evitar que el Antivirus corporativo lo bloquee.
        """
        try:
            import speech_recognition as sr
            sr_dir = os.path.dirname(os.path.abspath(sr.__file__))
            src_flac = os.path.join(sr_dir, "flac-win32.exe")
            if os.path.exists(src_flac):
                local_flac = os.path.join(self.config_manager.temp_dir, "flac-win32.exe")
                if not os.path.exists(local_flac):
                    shutil.copy2(src_flac, local_flac)
                # Forzar a SpeechRecognition a usar el ejecutable en nuestra carpeta segura
                sr.AudioData.get_flac_converter = staticmethod(lambda: local_flac)
                sr.get_flac_converter = lambda: local_flac
                log_console(f"[SyncAudio] Convertidor FLAC configurado en ruta segura: {local_flac}")
        except Exception as e:
            log_console(f"[SyncAudio] Aviso al preparar FLAC local: {e}")

    def _transcribe_fast_sr(self, audio_path: str, language: str = "es-MX") -> str:
        """
        Transcribe el archivo WAV usando SpeechRecognition con subproceso protegido para .exe.
        """
        import speech_recognition as sr
        log_console(f"[SyncAudio] Iniciando transcripción de: {audio_path}")
        recognizer = sr.Recognizer()
        lines = []

        with sr.AudioFile(audio_path) as source:
            offset = 0
            chunk_duration = 30
            while True:
                audio_data = recognizer.record(source, duration=chunk_duration)
                if len(audio_data.frame_data) == 0:
                    break
                try:
                    text = recognizer.recognize_google(audio_data, language=language)
                    if text and text.strip():
                        m = int(offset // 60)
                        s = int(offset % 60)
                        line_str = f"- **[{m:02d}:{s:02d}]** {text.strip()}"
                        log_console(f"  {line_str}")
                        lines.append(line_str)
                except sr.UnknownValueError:
                    log_console(f"[SyncAudio] Bloque {offset}s sin voz clara detectada.")
                except Exception as e:
                    log_console(f"[SyncAudio] Error en bloque {offset}s: {repr(e)}")
                    raise e
                offset += chunk_duration

        if not lines:
            return "_No se detectaron fragmentos de voz claros en la grabación._"
        return "\n".join(lines)

    def _generate_local_summary(self, transcription: str) -> str:
        lines = [
            line.split("]** ", 1)[-1]
            for line in transcription.splitlines()
            if "]** " in line
        ]
        total_interventions = len(lines)
        word_count = sum(len(line.split()) for line in lines)

        if total_interventions == 0:
            return "No hubo suficiente contenido hablado para extraer conclusiones."

        apertura = lines[0] if len(lines) >= 1 else ""
        cierre = " / ".join(lines[-2:]) if len(lines) >= 2 else lines[-1]

        return (
            f"- **Intervenciones detectadas:** {total_interventions} bloques de voz ({word_count} palabras aprox.)\n"
            f"- **Apertura de la sesión:** \"{apertura}\"\n"
            f"- **Cierre / Conclusión registrada:** \"{cierre}\"\n"
        )

    def process_recording(self, audio_path: str, duration_sec: float, status_callback=None) -> str:
        log_console("[SyncAudio] === Iniciando process_recording ===")
        if not audio_path or not os.path.exists(audio_path):
            log_console(f"[SyncAudio] Error: No se encontró el archivo temporal en {audio_path}")
            if status_callback:
                status_callback("Error: Audio no encontrado")
            return ""

        self.config_manager.config = self.config_manager._load_or_create_default()
        cfg = self.config_manager.get()

        out_dir = os.path.normpath(cfg["storage"]["output_directory"])
        keep_audio = cfg["storage"].get("keep_audio_file", True)
        ai_cfg = cfg["ai_settings"]
        local_cfg = cfg.get("transcription_local", {"model_size": "base", "language": "es"})

        os.makedirs(out_dir, exist_ok=True)
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        fecha_legible = datetime.now().strftime("%d/%m/%Y %H:%M")
        duracion_min = round(duration_sec / 60, 2)

        final_audio_name = f"Audio_{timestamp_str}.wav"
        final_audio_path = os.path.join(out_dir, final_audio_name)
        md_filename = f"Reunion_{timestamp_str}.md"
        md_filepath = os.path.join(out_dir, md_filename)

        # PASO 1: Guardar audio inmediatamente
        shutil.copy2(audio_path, final_audio_path)
        log_console(f"[SyncAudio] Audio copiado a: {final_audio_path}")

        initial_md = (
            f"# Registro de Reunión ({fecha_legible})\n\n"
            f"- **Duración:** {duracion_min} minutos\n"
            f"- **Estado:** ⏳ Procesando transcripción...\n"
            f"- **Archivo de Audio:** `{final_audio_name}`\n"
        )
        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write(initial_md)

        # RUTA A: MODO SIN IA EXTERNA
        if not ai_cfg.get("enabled", False):
            try:
                if status_callback:
                    status_callback("Transcribiendo audio...")

                lang = local_cfg.get("language", "es")
                lang_code = "es-MX" if lang == "es" else lang

                transcription = self._transcribe_fast_sr(final_audio_path, language=lang_code)
                local_conclusion = self._generate_local_summary(transcription)

                if os.path.exists(audio_path):
                    try:
                        os.remove(audio_path)
                    except Exception:
                        pass

                audio_note = f"`{final_audio_name}`"
                if not keep_audio and os.path.exists(final_audio_path):
                    os.remove(final_audio_path)
                    audio_note = "Eliminado tras procesar (según configuración)"

                md_content = (
                    f"# Registro de Reunión ({fecha_legible})\n\n"
                    f"- **Duración:** {duracion_min} minutos\n"
                    f"- **Modo:** Transcripción Automática (Sin IA Externa)\n"
                    f"- **Archivo de Audio:** {audio_note}\n\n"
                    f"---\n\n"
                    f"## Síntesis y Conclusión de la Reunión\n\n"
                    f"{local_conclusion}\n"
                    f"---\n\n"
                    f"## Transcripción Completa\n\n"
                    f"{transcription}\n"
                )

                with open(md_filepath, "w", encoding="utf-8") as f:
                    f.write(md_content)

                log_console(f"[SyncAudio] ¡Éxito! Archivo .md actualizado con transcripción: {md_filepath}")
                if status_callback:
                    status_callback("¡Transcripción Lista!")
                return md_filepath

            except Exception as e:
                err_trace = traceback.format_exc()
                log_console(f"[SyncAudio] EXCEPCIÓN EN EXE:\n{err_trace}")
                with open(md_filepath, "w", encoding="utf-8") as f:
                    f.write(
                        f"# Registro de Reunión ({fecha_legible})\n\n"
                        f"- **Duración:** {duracion_min} minutos\n"
                        f"- **Archivo de Audio Respaldado:** `{final_audio_name}`\n\n"
                        f"## Detalle Técnico en el Ejecutable\n"
                        f"```text\n{err_trace}\n```\n"
                    )
                if status_callback:
                    status_callback("Error (Ver .md)")
                return md_filepath

        # RUTA B: MODO IA EXTERNA ACTIVADO
        try:
            if status_callback:
                status_callback("IA: Transcribiendo...")

            if ai_cfg.get("api_key", "").strip():
                transcription = self._transcribe_cloud(final_audio_path, ai_cfg)
            else:
                lang = local_cfg.get("language", "es")
                lang_code = "es-MX" if lang == "es" else lang
                transcription = self._transcribe_fast_sr(final_audio_path, language=lang_code)

            if status_callback:
                status_callback("IA: Generando conclusión...")

            conclusion = self._generate_conclusion(transcription, ai_cfg)

            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except Exception:
                    pass

            audio_note = f"`{final_audio_name}`"
            if not keep_audio and os.path.exists(final_audio_path):
                os.remove(final_audio_path)
                audio_note = "Eliminado tras procesar"

            md_content = (
                f"# Reporte de Reunión ({fecha_legible})\n\n"
                f"- **Duración:** {duracion_min} minutos\n"
                f"- **Modelo Análisis IA:** `{ai_cfg.get('llm_model')}`\n"
                f"- **Audio Local:** {audio_note}\n\n"
                f"---\n\n"
                f"{conclusion}\n\n"
                f"---\n\n"
                f"## Transcripción Completa\n\n"
                f"{transcription}\n"
            )

            with open(md_filepath, "w", encoding="utf-8") as f:
                f.write(md_content)

            if status_callback:
                status_callback("¡Reporte IA Creado!")
            return md_filepath

        except Exception as e:
            err_trace = traceback.format_exc()
            log_console(f"[SyncAudio] Error en IA:\n{err_trace}")
            with open(md_filepath, "w", encoding="utf-8") as f:
                f.write(
                    f"# Error en Procesamiento IA ({fecha_legible})\n\n"
                    f"```text\n{err_trace}\n```\n\n"
                    f"**Tu grabación está a salvo en:** `{final_audio_name}`\n"
                )
            if status_callback:
                status_callback("Error IA (Ver .md)")
            return md_filepath

    def _transcribe_cloud(self, audio_path: str, ai_cfg: dict) -> str:
        base_url = ai_cfg.get("provider_base_url", "").rstrip("/")
        api_key = ai_cfg.get("api_key", "").strip()
        stt_model = ai_cfg.get("stt_model", "whisper-large-v3-turbo").strip()

        url = f"{base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        with open(audio_path, "rb") as audio_file:
            files = {"file": (os.path.basename(audio_path), audio_file, "audio/wav")}
            data = {"model": stt_model, "response_format": "text"}
            response = requests.post(url, headers=headers, files=files, data=data, timeout=300)

        if response.status_code != 200:
            raise RuntimeError(f"Error STT ({response.status_code}): {response.text}")

        try:
            json_resp = response.json()
            return json_resp.get("text", response.text).strip()
        except Exception:
            return response.text.strip()

    def _generate_conclusion(self, transcription: str, ai_cfg: dict) -> str:
        if not transcription:
            return "_No se detectó voz en la grabación._"

        base_url = ai_cfg.get("provider_base_url", "").rstrip("/")
        api_key = ai_cfg.get("api_key", "").strip()
        llm_model = ai_cfg.get("llm_model", "llama-3.3-70b-versatile").strip()
        sys_prompt = ai_cfg.get("system_prompt", "Resume y genera conclusiones de esta reunión.")

        url = f"{base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "model": llm_model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"Transcripción de la reunión:\n\n{transcription}"}
            ],
            "temperature": 0.3
        }

        response = requests.post(url, headers=headers, json=payload, timeout=180)
        if response.status_code != 200:
            raise RuntimeError(f"Error LLM ({response.status_code}): {response.text}")

        data = response.json()
        return data["choices"][0]["message"]["content"].strip()