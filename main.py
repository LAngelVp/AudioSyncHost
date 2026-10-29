import threading
import keyboard
from config_manager import ConfigManager
from audio_recorder import AudioRecorder
from ai_processor import AIProcessor
from ui import MainWindow


class ApplicationController:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.recorder = AudioRecorder(temp_dir=self.config_manager.temp_dir)
        self.ai_processor = AIProcessor(self.config_manager)
        self.is_hidden = False

        self.app = MainWindow(
            config_manager=self.config_manager,
            on_start=self.handle_start,
            on_pause=self.handle_pause,
            on_finish=self.handle_finish,
            on_hide=self.toggle_stealth_mode
        )

        self._register_hotkeys()

    def _register_hotkeys(self):
        hotkey = self.config_manager.get()["stealth"].get("hotkey_toggle_ui", "ctrl+alt+s")
        try:
            keyboard.add_hotkey(hotkey, lambda: self.app.after(0, self.toggle_stealth_mode))
        except Exception:
            pass

    def toggle_stealth_mode(self):
        """
        Oculta la aplicación de la Barra de Tareas y del menú Alt+Tab.
        Al estar compilada sin consola, Windows la mueve a 'Procesos en segundo plano'.
        """
        if not self.is_hidden:
            self.app.withdraw()
            self.is_hidden = True
        else:
            self.app.deiconify()
            self.app.lift()
            self.app.focus_force()
            self.is_hidden = False

    def handle_start(self):
        self.recorder.start()
        self.app.set_status("Grabando...", "#2ECC71")
        self.app.btn_start.configure(state="disabled")
        self.app.btn_pause.configure(state="normal", text="Parar")
        self.app.btn_finish.configure(state="normal")

    def handle_pause(self):
        status = self.recorder.pause()
        if status == "Pausado":
            self.app.set_status("Pausado", "#F1C40F")
            self.app.btn_pause.configure(text="Reanudar")
        else:
            self.app.set_status("Grabando...", "#2ECC71")
            self.app.btn_pause.configure(text="Parar")

    def handle_finish(self):
        self.app.btn_start.configure(state="disabled")
        self.app.btn_pause.configure(state="disabled", text="Parar")
        self.app.btn_finish.configure(state="disabled")
        self.app.set_status("Cerrando audio...", "#3498DB")

        def background_pipeline():
            audio_path, duration = self.recorder.stop()

            def update_ui_status(msg):
                self.app.after(0, lambda: self.app.set_status(msg, "#3498DB"))

            self.ai_processor.process_recording(
                audio_path=audio_path,
                duration_sec=duration,
                status_callback=update_ui_status
            )

            self.app.after(0, lambda: self.app.btn_start.configure(state="normal"))

        threading.Thread(target=background_pipeline, daemon=True).start()

    def run(self):
        self.app.mainloop()


if __name__ == "__main__":
    controller = ApplicationController()
    controller.run()