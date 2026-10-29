# Especificación de Arquitectura del Sistema (Spec-Driven Development)

**Nombre del Proyecto:** SyncAudio (Binario: `AudioSyncHost.exe`)
**Tipo de Sistema:** Aplicación de Escritorio Ultraligera de Captura, Transcripción y Síntesis en Segundo Plano
**Patrón Arquitectónico:** Controlador Guiado por Eventos + Pipeline Multihilo Asíncrono
**Stack Tecnológico:** Python 3.12+, CustomTkinter, PyAudioWPatch, NumPy, SpeechRecognition, Requests, PyInstaller

---

## 1. Visión General y Propósito
**SyncAudio** es una herramienta de escritorio de bajo consumo de recursos diseñada para capturar simultáneamente la entrada del micrófono del usuario y la salida de audio interno del sistema operativo (WASAPI Loopback) durante reuniones virtuales (Google Meet, Microsoft Teams, Zoom, Webex, etc.).

Al finalizar la sesión, el sistema respalda de inmediato la evidencia de audio, transcribe la conversación completa con marcas de tiempo y genera un documento estructurado en formato Markdown (`.md`) con conclusiones directamente en carpetas locales sincronizadas con servicios en la nube (OneDrive, Google Drive o iCloud). Cuenta con un motor dual que permite operar **sin IA externa** (síntesis local automática) o **con IA externa** (conectándose a cualquier endpoint compatible con OpenAI/Groq/Ollama).

---

## 2. Requerimientos del Sistema

### 2.1. Requerimientos Funcionales (RF)
* **RF-01 (Control de Grabación):** La ventana principal provee tres estados mediante botones dedicados: *Iniciar* (abre los flujos de audio), *Parar/Reanudar* (pausa la escritura en disco sin cerrar el archivo) y *Terminar* (cierra el archivo `.wav` y dispara el hilo de transcripción y generación `.md`).
* **RF-02 (Ejecución en Segundo Plano y Ocultamiento):** Incluye un botón para ocultar la ventana (`withdraw()`), eliminando su icono de la Barra de Tareas y del selector `Alt+Tab`. El control se recupera en cualquier momento mediante un atajo de teclado global configurable (por defecto `Ctrl + Alt + S`).
* **RF-03 (Configuración Persistente vía UI):** Un botón de engrane (`⚙`) despliega una ventana modal (`SettingsModal`) que permite seleccionar la ruta de almacenamiento (OneDrive/Google Drive/iCloud), elegir si se conserva el archivo `.wav` y configurar los parámetros de conexión del modelo de IA.
* **RF-04 (Transcripción Garantizada y Respaldo Inmediato):** Al concluir una grabación, el sistema copia el archivo `.wav` y crea el archivo `.md` en la carpeta destino antes de iniciar el procesamiento pesado, garantizando cero pérdida de información ante cierres inesperados.
* **RF-05 (Procesamiento de IA Condicional):**
  * *Modo IA Desactivado:* Transcribe el audio en bloques con marcas de tiempo `[MM:SS]` y genera una síntesis estadística y de apertura/cierre de forma local.
  * *Modo IA Activado:* Transcribe el audio (vía API STT o motor local) y envía el texto a un LLM junto con el *System Prompt* configurado para redactar el Resumen Ejecutivo, Puntos Clave, Acuerdos y Conclusión General.

### 2.2. Requerimientos No Funcionales (RNF)
* **RNF-01 (Bajo Consumo de Recursos):** Grabación mediante *Disk Streaming* directo en bloques de 250 ms a 16 kHz Mono PCM 16-bit. El consumo de RAM del buffer de audio se mantiene constante (< 15 MB) sin importar si la reunión dura 5 minutos o 3 horas.
* **RNF-02 (Discreción en el Gestor de Tareas):** Compilación como ejecutable único sin ventana de consola (`console=False`) y bajo el nombre neutro `AudioSyncHost.exe`, logrando que Windows lo clasifique dentro de la sección *"Procesos en segundo plano"*.
* **RNF-03 (Independencia de Archivos `.env`):** Ninguna configuración depende de variables de entorno externas ni de `python-dotenv`. Todo reside en `config.json` resuelto dinámicamente junto al ejecutable (`sys.executable`).
* **RNF-04 (Compatibilidad con Redes Corporativas y Antivirus):** Desactivación de protocolos propietarios bloqueados por firewalls (como Xet/CAS), empaquetado sin compresión agresiva (`upx=False`) y extracción segura de binarios auxiliares fuera de `%TEMP%`.

---

## 3. Estructura de Archivos del Proyecto

```text
proyecto_grabador/
│
├── main.py                # 1. Punto de entrada, redirección de flujos Nulos y controlador principal
├── ui.py                  # 2. Micro-ventana (CustomTkinter) y ventana modal de configuración
├── audio_recorder.py      # 3. Motor concurrente de captura dual (Micrófono + WASAPI Loopback)
├── ai_processor.py        # 4. Motor de transcripción, parche de subprocesos Win32 y cliente IA
├── config_manager.py      # 5. Gestor de persistencia JSON compatible con PyInstaller (sys.frozen)
│
├── config.json            # 6. (Autogenerado) Almacena rutas de nube, hotkeys y credenciales IA
├── requirements.txt       # 7. Lista estricta de dependencias del proyecto
├── build.spec             # 8. Especificación de empaquetado para PyInstaller
└── ARCHITECTURE_SPEC.md   # 9. Documentación de arquitectura del sistema (este documento)
```

---

## 4. Arquitectura Detallada por Módulo

### 4.1. `config_manager.py` (Persistencia y Resolución de Entorno)
Resuelve la diferencia de rutas entre el entorno de desarrollo (`.py`) y el binario empaquetado (`.exe`).
* **Detección de Empaquetado:** Evalúa `getattr(sys, 'frozen', False)`. Cuando corre como `.exe`, fija `base_dir` en `os.path.dirname(sys.executable)` para evitar que `config.json` y la carpeta `temp_audio/` se escriban en el directorio temporal efímero `_MEIPASS` de PyInstaller.
* **Contrato de Datos (`config.json`):**
  ```json
  {
      "storage": {
          "output_directory": "C:/Users/Usuario/OneDrive/NotasReuniones",
          "keep_audio_file": true
      },
      "stealth": {
          "hotkey_toggle_ui": "ctrl+alt+s"
      },
      "transcription_local": {
          "model_size": "base",
          "language": "es"
      },
      "ai_settings": {
          "enabled": false,
          "provider_base_url": "[https://api.groq.com/openai/v1](https://api.groq.com/openai/v1)",
          "api_key": "",
          "stt_model": "whisper-large-v3-turbo",
          "llm_model": "llama-3.3-70b-versatile",
          "system_prompt": "Eres un asistente experto en análisis de reuniones..."
      }
  }
  ```

### 4.2. `audio_recorder.py` (Captura Concurrente y Mezcla DSP)
Ejecuta un hilo demonio (`threading.Thread(daemon=True)`) gobernado por dos banderas atómicas (`threading.Event`): `is_recording` e `is_paused`.
* **Captura Dual Asíncrona:**
  1. **Canal de Entrada (Micrófono):** Obtiene el dispositivo por defecto mediante `p.get_default_input_device_info()` y registra el callback `mic_cb`.
  2. **Canal del Sistema (WASAPI Loopback):** Obtiene la salida de audio activa de Windows mediante `p.get_default_wasapi_loopback()` y registra el callback `sys_cb`. Permite grabar lo que dicen los participantes en Meet/Teams incluso cuando el usuario utiliza audífonos.
* **Remuestreo y Mezcla Matemática (`numpy`):**
  * Convierte cualquier frecuencia de muestreo nativa (44.1 kHz o 48 kHz estéreo) a **16,000 Hz, 1 Canal (Mono), 16-bit PCM**.
  * Pondera y suma ambos flujos con protección contra saturación (*hard clipping*):
    $$\text{mixed} = \text{clip}\left((\text{mic\_data} \times 0.7) + (\text{sys\_data} \times 0.7), -32768, 32767\right)$$
  * Escribe bloques cada 250 ms directamente en disco mediante la librería estándar `wave`.

### 4.3. `ai_processor.py` (Motor de Transcripción, Síntesis y Blindaje Win32)
Opera en un hilo secundario al presionar *Terminar* para mantener la interfaz gráfica fluida.
* **Blindaje para Ejecutables sin Consola (`_SafeWindowlessPopen`):**
  * En Windows, cuando un `.exe` se compila con `console=False`, las llamadas internas a `subprocess.Popen` fallan si intentan heredar descriptores `stdin`/`stdout` nulos o abren ventanas emergentes de consola. Se intercepta `subprocess.Popen` inyectando la bandera `CREATE_NO_WINDOW`, `SW_HIDE` y `stdin=subprocess.DEVNULL`.
* **Aislamiento del Convertidor FLAC (`_ensure_flac_outside_temp`):**
  * Extrae `flac-win32.exe` desde el paquete interno hacia `temp_audio/flac-win32.exe` (fuera de `%TEMP%\_MEI...`) para evitar bloqueos por políticas de seguridad corporativas (EDR/Antivirus).
* **Pipeline de Ejecución en 3 Etapas:**
  1. **Etapa 1 (Persistencia Inmediata):** Copia el archivo `.wav` a la carpeta de destino y genera el archivo `Reunion_YYYY-MM-DD_HH-MM-SS.md` con estado `⏳ Procesando transcripción...`.
  2. **Etapa 2 (Transcripción Segmentada):** Procesa el audio en ventanas de 30 segundos etiquetando cada intervención con su marca de tiempo `- **[MM:SS]** Texto...`.
  3. **Etapa 3 (Generación de Conclusión):**
     * Si `ai_settings.enabled == false`: Ejecuta `_generate_local_summary()` calculando intervenciones, conteo de palabras, apertura y acuerdos de cierre.
     * Si `ai_settings.enabled == true`: Realiza peticiones HTTP REST (`requests`) a los endpoints `/audio/transcriptions` y `/chat/completions` configurados, inyectando la transcripción y el `system_prompt` para obtener el análisis completo.

### 4.4. `ui.py` (Presentación en CustomTkinter)
* **`MainWindow` (330x125 px):** Ventana compacta con propiedad `-topmost` activa. Contiene el indicador dinámico de estado (`● Listo`, `● Grabando...`, `● Pausado`, `● Transcribiendo...`), el botón de ocultamiento a segundo plano, el botón de engrane y la botonera de control con máquina de estados (habilitación/deshabilitación mutua para impedir dobles grabaciones).
* **`SettingsModal` (480x580 px):** Ventana hija modal (`CTkToplevel` con `grab_set()`). Integra `filedialog.askdirectory` para elegir carpetas de OneDrive/Drive/iCloud y activa o desactiva dinámicamente los campos de texto de IA según el estado del `CTkSwitch`.

### 4.5. `main.py` (Orquestador y Seguridad de Flujos Estándar)
* **Redirección de `sys.stdout` y `sys.stderr`:** Al inicio del script verifica si `sys.stdout is None` (condición nativa de PyInstaller con `console=False`). De ser así, redirige ambos flujos al archivo `syncaudio.log` para impedir excepciones `AttributeError: 'NoneType' object has no attribute 'flush'`.
* **Gestión de Visibilidad y Thread-Safety:** Registra el atajo global con `keyboard.add_hotkey` y utiliza `self.app.after(0, ...)` para delegar cualquier actualización visual al hilo principal del bucle de eventos de Tkinter.

---

## 5. Flujo de Datos extremo a extremo (Pipeline)

```text
[Micrófono] ─────────┐
                     ├──> [Normalización 16kHz Mono + Mezcla NumPy] ──> [Escritura directa .wav (Disco)]
[Audio Sistema] ─────┘                                                               │
(Meet / Teams)                                                                       ▼
                                                                       [Usuario pulsa "Terminar"]
                                                                                     │
                                                       ┌─────────────────────────────┴─────────────────────────────┐
                                                       ▼                                                           ▼
                                            [Modo IA Desactivado]                                        [Modo IA Activado]
                                                       │                                                           │
                                       1. Respalda .wav y crea .md inicial                         1. Respalda .wav y crea .md inicial
                                       2. Transcribe por bloques [MM:SS]                           2. Transcribe (Cloud STT o Local)
                                       3. Genera Síntesis y Cierre Local                           3. Envía a LLM (/chat/completions)
                                       4. Actualiza .md en carpeta Nube                            4. Actualiza .md con Conclusión IA
```

---

## 6. Estrategia de Empaquetado y Despliegue (`build.spec`)

Para compilar el proyecto desde cualquier entorno sin errores de importaciones faltantes ni bloqueos de antivirus:

1. **Recolección Automática de Recursos (`collect_all`):** Empaqueta automáticamente los temas visuales JSON de `customtkinter`, el binario de conversión de `speech_recognition`, los certificados SSL de `certifi` y las librerías dinámicas de `pyaudiowpatch`.
2. **Importaciones Ocultas Explícitas (`hiddenimports`):** Incluye los módulos nativos de procesamiento de audio de la librería estándar de Python 3.12 (`aifc`, `chunk`, `audioop`, `wave`).
3. **Desactivación de UPX (`upx=False`):** Evita falsos positivos en antivirus corporativos al no alterar la firma de las DLLs de audio de Windows.
4. **Identidad de Proceso (`name='AudioSyncHost'`, `console=False`):** Genera un único ejecutable silencioso en `dist/AudioSyncHost.exe`.

### Comandos de Mantenimiento y Compilación

* **Instalación de dependencias:**
  ```bash
  python -m pip install -r requirements.txt
  ```
* **Ejecución en entorno de desarrollo:**
  ```bash
  python main.py
  ```
* **Compilación limpia a producción (`.exe`):**
  ```bash
  python -m PyInstaller --clean -y build.spec
  ```