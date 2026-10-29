import os
import time
import wave
import threading
import numpy as np
import pyaudiowpatch as pyaudio
from datetime import datetime


class AudioRecorder:
    TARGET_RATE = 16000  # 16kHz Mono es el estándar ideal para Whisper y bajo peso

    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir
        self.is_recording = threading.Event()
        self.is_paused = threading.Event()

        self._thread = None
        self._mic_latest = np.zeros(0, dtype=np.float32)
        self._sys_latest = np.zeros(0, dtype=np.float32)
        self._lock = threading.Lock()
        self.current_filepath = None
        self.start_time = None

    def _resample_and_mono(self, raw_bytes: bytes, channels: int, src_rate: int) -> np.ndarray:
        """Convierte cualquier flujo de audio entrante a Mono 16kHz en float32."""
        if not raw_bytes:
            return np.zeros(0, dtype=np.float32)

        data = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
        if channels > 1:
            data = data.reshape(-1, channels).mean(axis=1)

        if src_rate != self.TARGET_RATE and len(data) > 0:
            duration = len(data) / src_rate
            target_len = int(duration * self.TARGET_RATE)
            if target_len > 0:
                x_old = np.linspace(0, duration, num=len(data), endpoint=False)
                x_new = np.linspace(0, duration, num=target_len, endpoint=False)
                data = np.interp(x_new, x_old, data).astype(np.float32)
        return data

    def start(self) -> bool:
        if self.is_recording.is_set():
            if self.is_paused.is_set():
                self.is_paused.clear()  # Reanudar si estaba en pausa
            return True

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.current_filepath = os.path.join(self.temp_dir, f"rec_{timestamp}.wav")

        self.is_recording.set()
        self.is_paused.clear()
        self.start_time = time.time()

        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()
        return True

    def pause(self):
        """Pausa o reanuda la grabación activa."""
        if self.is_recording.is_set():
            if self.is_paused.is_set():
                self.is_paused.clear()
                return "Grabando..."
            else:
                self.is_paused.set()
                return "Pausado"
        return "Listo"

    def stop(self) -> tuple[str, float]:
        """Detiene la grabación, cierra el archivo WAV y devuelve (ruta_archivo, duracion_segundos)."""
        if not self.is_recording.is_set():
            return None, 0.0

        self.is_recording.clear()
        self.is_paused.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

        duration = time.time() - self.start_time if self.start_time else 0.0
        return self.current_filepath, duration

    def _record_loop(self):
        p = pyaudio.PyAudio()
        mic_stream = None
        sys_stream = None

        mic_queue = []
        sys_queue = []

        # 1. Configurar Micrófono por defecto
        try:
            mic_info = p.get_default_input_device_info()
            mic_rate = int(mic_info["defaultSampleRate"])
            mic_ch = max(1, int(mic_info["maxInputChannels"]))

            def mic_cb(in_data, frame_count, time_info, status):
                if self.is_recording.is_set() and not self.is_paused.is_set():
                    arr = self._resample_and_mono(in_data, mic_ch, mic_rate)
                    with self._lock:
                        mic_queue.append(arr)
                return (None, pyaudio.paContinue)

            mic_stream = p.open(
                format=pyaudio.paInt16,
                channels=mic_ch,
                rate=mic_rate,
                input=True,
                input_device_index=mic_info["index"],
                frames_per_buffer=int(mic_rate * 0.1),
                stream_callback=mic_cb
            )
            mic_stream.start_stream()
        except Exception:
            mic_stream = None

        # 2. Configurar Loopback del Sistema (Meet, Teams, Zoom)
        try:
            loopback_info = p.get_default_wasapi_loopback()
            sys_rate = int(loopback_info["defaultSampleRate"])
            sys_ch = max(1, int(loopback_info["maxInputChannels"]))

            def sys_cb(in_data, frame_count, time_info, status):
                if self.is_recording.is_set() and not self.is_paused.is_set():
                    arr = self._resample_and_mono(in_data, sys_ch, sys_rate)
                    with self._lock:
                        sys_queue.append(arr)
                return (None, pyaudio.paContinue)

            sys_stream = p.open(
                format=pyaudio.paInt16,
                channels=sys_ch,
                rate=sys_rate,
                input=True,
                input_device_index=loopback_info["index"],
                frames_per_buffer=int(sys_rate * 0.1),
                stream_callback=sys_cb
            )
            sys_stream.start_stream()
        except Exception:
            sys_stream = None

        # 3. Escritura directa a disco en bloques de 250ms (Cero acumulación en RAM)
        chunk_samples = int(self.TARGET_RATE * 0.25)
        with wave.open(self.current_filepath, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16 bits = 2 bytes
            wf.setframerate(self.TARGET_RATE)

            while self.is_recording.is_set():
                time.sleep(0.25)
                if self.is_paused.is_set():
                    continue

                with self._lock:
                    mic_data = np.concatenate(mic_queue) if mic_queue else np.zeros(0, dtype=np.float32)
                    sys_data = np.concatenate(sys_queue) if sys_queue else np.zeros(0, dtype=np.float32)
                    mic_queue.clear()
                    sys_queue.clear()

                max_len = max(len(mic_data), len(sys_data), chunk_samples)
                if len(mic_data) == 0 and len(sys_data) == 0:
                    mixed = np.zeros(chunk_samples, dtype=np.int16)
                else:
                    if len(mic_data) < max_len:
                        mic_data = np.pad(mic_data, (0, max_len - len(mic_data)))
                    if len(sys_data) < max_len:
                        sys_data = np.pad(sys_data, (0, max_len - len(sys_data)))

                    combined = np.clip((mic_data * 0.7) + (sys_data * 0.7), -32768, 32767)
                    mixed = combined.astype(np.int16)

                wf.writeframes(mixed.tobytes())

        # Limpieza segura de dispositivos
        for st in (mic_stream, sys_stream):
            if st is not None:
                try:
                    st.stop_stream()
                    st.close()
                except Exception:
                    pass
        p.terminate()