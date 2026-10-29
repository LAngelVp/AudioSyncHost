import customtkinter as ctk
from tkinter import filedialog

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class SettingsModal(ctk.CTkToplevel):
    def __init__(self, parent, config_manager):
        super().__init__(parent)
        self.config_manager = config_manager
        self.cfg = self.config_manager.get()

        self.title("Configuración de Ruta e IA")
        self.geometry("480x580")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build_form()

    def _build_form(self):
        pad_x = 16

        # --- SECCIÓN 1: RUTA DE ALMACENAMIENTO (OneDrive / Drive / iCloud) ---
        lbl_storage = ctk.CTkLabel(self, text="Carpeta de Destino (.md)", font=("Segoe UI", 14, "bold"))
        lbl_storage.pack(anchor="w", padx=pad_x, pady=(15, 5))

        frame_path = ctk.CTkFrame(self, fg_color="transparent")
        frame_path.pack(fill="x", padx=pad_x, pady=2)

        self.entry_path = ctk.CTkEntry(frame_path, width=330)
        self.entry_path.pack(side="left", padx=(0, 8))
        self.entry_path.insert(0, self.cfg["storage"].get("output_directory", ""))

        btn_browse = ctk.CTkButton(frame_path, text="Explorar...", width=95, command=self._browse_folder)
        btn_browse.pack(side="left")

        self.chk_keep_audio = ctk.CTkCheckBox(
            self, text="Conservar archivo de audio (.wav) junto al .md"
        )
        self.chk_keep_audio.pack(anchor="w", padx=pad_x, pady=(8, 10))
        if self.cfg["storage"].get("keep_audio_file", False):
            self.chk_keep_audio.select()

        # --- SECCIÓN 2: ATAJO DE MODO OCULTO ---
        frame_hotkey = ctk.CTkFrame(self, fg_color="transparent")
        frame_hotkey.pack(fill="x", padx=pad_x, pady=4)
        ctk.CTkLabel(frame_hotkey, text="Atajo para Mostrar/Ocultar app:").pack(side="left")
        self.entry_hotkey = ctk.CTkEntry(frame_hotkey, width=140)
        self.entry_hotkey.pack(side="right")
        self.entry_hotkey.insert(0, self.cfg["stealth"].get("hotkey_toggle_ui", "ctrl+alt+s"))

        # --- SECCIÓN 3: CONFIGURACIÓN DE INTELIGENCIA ARTIFICIAL (OPCIONAL) ---
        lbl_ai = ctk.CTkLabel(self, text="Conexión de Inteligencia Artificial", font=("Segoe UI", 14, "bold"))
        lbl_ai.pack(anchor="w", padx=pad_x, pady=(15, 5))

        self.switch_ai = ctk.CTkSwitch(
            self,
            text="Habilitar Transcripción y Conclusión con IA",
            command=self._toggle_ai_fields
        )
        self.switch_ai.pack(anchor="w", padx=pad_x, pady=5)
        if self.cfg["ai_settings"].get("enabled", False):
            self.switch_ai.select()

        # Contenedor de campos IA
        self.ai_frame = ctk.CTkFrame(self)
        self.ai_frame.pack(fill="both", expand=True, padx=pad_x, pady=8)

        # Base URL
        ctk.CTkLabel(self.ai_frame, text="Base URL (OpenAI / Groq / Local):").pack(anchor="w", padx=12, pady=(8, 0))
        self.entry_url = ctk.CTkEntry(self.ai_frame, width=420)
        self.entry_url.pack(padx=12, pady=(2, 6))
        self.entry_url.insert(0, self.cfg["ai_settings"].get("provider_base_url", ""))

        # API Key
        ctk.CTkLabel(self.ai_frame, text="API Key:").pack(anchor="w", padx=12, pady=(4, 0))
        self.entry_key = ctk.CTkEntry(self.ai_frame, width=420, show="*")
        self.entry_key.pack(padx=12, pady=(2, 6))
        self.entry_key.insert(0, self.cfg["ai_settings"].get("api_key", ""))

        # Modelos STT y LLM en una fila
        models_row = ctk.CTkFrame(self.ai_frame, fg_color="transparent")
        models_row.pack(fill="x", padx=12, pady=4)

        col_stt = ctk.CTkFrame(models_row, fg_color="transparent")
        col_stt.pack(side="left", fill="x", expand=True, padx=(0, 5))
        ctk.CTkLabel(col_stt, text="Modelo Audio (STT):").pack(anchor="w")
        self.entry_stt = ctk.CTkEntry(col_stt)
        self.entry_stt.pack(fill="x", pady=2)
        self.entry_stt.insert(0, self.cfg["ai_settings"].get("stt_model", ""))

        col_llm = ctk.CTkFrame(models_row, fg_color="transparent")
        col_llm.pack(side="left", fill="x", expand=True, padx=(5, 0))
        ctk.CTkLabel(col_llm, text="Modelo Conclusión (LLM):").pack(anchor="w")
        self.entry_llm = ctk.CTkEntry(col_llm)
        self.entry_llm.pack(fill="x", pady=2)
        self.entry_llm.insert(0, self.cfg["ai_settings"].get("llm_model", ""))

        # Prompt del sistema
        ctk.CTkLabel(self.ai_frame, text="Instrucciones para la Conclusión (Prompt):").pack(anchor="w", padx=12, pady=(6, 0))
        self.txt_prompt = ctk.CTkTextbox(self.ai_frame, height=65)
        self.txt_prompt.pack(fill="x", padx=12, pady=(2, 10))
        self.txt_prompt.insert("1.0", self.cfg["ai_settings"].get("system_prompt", ""))

        # Botón Guardar
        btn_save = ctk.CTkButton(self, text="Guardar Configuración", fg_color="#1f8b4c", hover_color="#166536", command=self._save)
        btn_save.pack(fill="x", padx=pad_x, pady=(5, 15))

        self._toggle_ai_fields()

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Seleccionar carpeta (OneDrive, Google Drive, iCloud, etc.)")
        if folder:
            self.entry_path.delete(0, "end")
            self.entry_path.insert(0, folder)

    def _toggle_ai_fields(self):
        state = "normal" if self.switch_ai.get() == 1 else "disabled"
        for widget in (self.entry_url, self.entry_key, self.entry_stt, self.entry_llm, self.txt_prompt):
            widget.configure(state=state)

    def _save(self):
        self.cfg["storage"]["output_directory"] = self.entry_path.get().strip()
        self.cfg["storage"]["keep_audio_file"] = bool(self.chk_keep_audio.get())
        self.cfg["stealth"]["hotkey_toggle_ui"] = self.entry_hotkey.get().strip().lower()

        self.cfg["ai_settings"]["enabled"] = bool(self.switch_ai.get())
        self.cfg["ai_settings"]["provider_base_url"] = self.entry_url.get().strip()
        self.cfg["ai_settings"]["api_key"] = self.entry_key.get().strip()
        self.cfg["ai_settings"]["stt_model"] = self.entry_stt.get().strip()
        self.cfg["ai_settings"]["llm_model"] = self.entry_llm.get().strip()
        self.cfg["ai_settings"]["system_prompt"] = self.txt_prompt.get("1.0", "end").strip()

        self.config_manager.save_config(self.cfg)
        self.destroy()


class MainWindow(ctk.CTk):
    def __init__(self, config_manager, on_start, on_pause, on_finish, on_hide):
        super().__init__()
        self.config_manager = config_manager
        self.on_start = on_start
        self.on_pause = on_pause
        self.on_finish = on_finish
        self.on_hide = on_hide

        self.title("SyncAudio")
        self.geometry("330x125")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self._build_ui()

    def _build_ui(self):
        # Fila superior: Estado + Botón Segundo Plano + Botón Engrane
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=12, pady=(10, 4))

        self.lbl_status = ctk.CTkLabel(
            top_bar, text="● Listo", text_color="#A0A0A0", font=("Segoe UI", 13, "bold")
        )
        self.lbl_status.pack(side="left")

        btn_gear = ctk.CTkButton(
            top_bar, text="⚙", width=32, height=28,
            fg_color="#3B3B3B", hover_color="#505050",
            command=self._open_settings
        )
        btn_gear.pack(side="right", padx=(5, 0))

        btn_stealth = ctk.CTkButton(
            top_bar, text="Ocultar (2do Plano)", width=120, height=28,
            fg_color="#2B4C7E", hover_color="#1E3557",
            font=("Segoe UI", 11),
            command=self.on_hide
        )
        btn_stealth.pack(side="right")

        # Fila inferior: Botones Iniciar, Parar (Pausa), Terminar
        controls_bar = ctk.CTkFrame(self, fg_color="transparent")
        controls_bar.pack(fill="x", padx=12, pady=(12, 10))

        self.btn_start = ctk.CTkButton(
            controls_bar, text="Iniciar", width=95, height=38,
            fg_color="#1f8b4c", hover_color="#166536",
            font=("Segoe UI", 12, "bold"),
            command=self.on_start
        )
        self.btn_start.pack(side="left", expand=True, padx=2)

        self.btn_pause = ctk.CTkButton(
            controls_bar, text="Parar", width=95, height=38,
            fg_color="#b8860b", hover_color="#8b6508",
            font=("Segoe UI", 12, "bold"),
            state="disabled",
            command=self.on_pause
        )
        self.btn_pause.pack(side="left", expand=True, padx=2)

        self.btn_finish = ctk.CTkButton(
            controls_bar, text="Terminar", width=95, height=38,
            fg_color="#a82020", hover_color="#7a1515",
            font=("Segoe UI", 12, "bold"),
            state="disabled",
            command=self.on_finish
        )
        self.btn_finish.pack(side="left", expand=True, padx=2)

    def set_status(self, text: str, color: str = "#A0A0A0"):
        self.lbl_status.configure(text=f"● {text}", text_color=color)

    def _open_settings(self):
        SettingsModal(self, self.config_manager)