# noqa

# win_service.py
# Servicio de Windows para "icon3-integration" que reutiliza tu comando results() de run.py.
# - TCP: llama results() una vez (bloquea dentro).
# - FILE: ejecuta results() en bucle cada INTERVAL segundos.

import os
import socket
import sys  # noqa: F401,E501
import threading
import time

import servicemanager  # noqa: F401,E501
import win32event  # noqa: F401,E501
import win32service  # noqa: F401,E501
import win32serviceutil  # noqa: F401,E501
import yaml


def resource_path(relative_path: str) -> str:
    """Devuelve la ruta absoluta a un recurso, ya sea ejecutando como .exe o en desarrollo"""
    if hasattr(sys, "_MEIPASS"):
        # Si es un ejecutable generado por PyInstaller
        base_path = sys._MEIPASS
    else:
        # Si es ejecución normal (dev)
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def load_cfg():
    config_path = resource_path("app/configs/settings.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# Importa tu CLI; importante: que run.py NO ejecute app()
# al importar (debe estar bajo if __name__ == "__main__")
try:
    from run import results as run_results

    # Si prefieres evitar cambiar run.py, no toques nada.
except Exception as e:
    raise RuntimeError(f"No se pudo importar results() desde run.py: {e}")


# Lee tu config para detectar FILE/TCP e intervalo
def _load_mode_and_interval(default_interval=10):
    """
    Devuelve (mode, interval_seconds)
    - mode: "file" o "tcp" (según cfg["transport"]["results"]["type"])
    - interval_seconds: para modo FILE; si hay campo en settings,
    úsalo; si no, default_interval
    """
    try:
        # Ajusta este import a tu proyecto si el loader vive en otra ruta
        cfg = load_cfg()
        mode = str(cfg["transport"]["results"]["type"]).lower()
        interval = default_interval
        # (Opcional) si guardas intervalo en settings, léelo aquí:
        # p.ej., cfg["transport"]["results"]["file"]["interval_seconds"]
        try:
            interval = int(
                cfg["transport"]["results"]["file"].get("interval_seconds", default_interval)
            )
        except Exception:
            pass
        return mode, interval
    except Exception as e:
        # Si falla cargar config, cae en TCP por seguridad
        # (no hace loop) y usa default_interval
        servicemanager.LogErrorMsg(f"[icon3-integration] No se pudo leer config: {e}")
        return "tcp", default_interval


class Icon3IntegrationService(win32serviceutil.ServiceFramework):
    _svc_name_ = "Icon3Integration"
    _svc_display_name_ = "Icon3 Integration Service"
    _svc_description_ = "Procesa resultados HL7 (FILE en bucle; TCP continuo)."

    def __init__(self, args):
        super().__init__(args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.running = True
        socket.setdefaulttimeout(60)

        self.worker_thread = None
        self.mode, self.file_interval = _load_mode_and_interval(default_interval=10)

    def SvcDoRun(self):
        servicemanager.LogInfoMsg(f"[icon3-integration] Service starting (mode={self.mode})")

        def worker():
            try:
                if self.mode == "file":
                    self._loop_file_mode()
                else:
                    # TCP (o fallback): corre una sola vez; bloquea hasta terminar.
                    run_results()
            except Exception as e:
                servicemanager.LogErrorMsg(f"[icon3-integration] Error en worker: {e}")

        self.worker_thread = threading.Thread(
            target=worker, name="icon3-service-worker", daemon=True
        )
        self.worker_thread.start()

        # Espera señal de STOP desde el Service Control Manager
        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

        # Señaliza parada
        self.running = False

        # Espera suave a que el hilo termine (si estaba en FILE loop, saldrá en pocos segundos)
        join_deadline = time.time() + 15
        while self.worker_thread.is_alive() and time.time() < join_deadline:
            time.sleep(0.5)

        servicemanager.LogInfoMsg("[icon3-integration] Service stopped")

    def SvcStop(self):
        servicemanager.LogInfoMsg("[icon3-integration] Service stopping...")
        win32event.SetEvent(self.hWaitStop)

    # ---------- helpers ----------
    def _loop_file_mode(self):
        """
        Modo FILE: ejecuta 'pasadas' periódicas llamando run_results() y
        espera file_interval segundos entre cada una.
        Al recibir STOP, el bucle sale entre iteraciones.
        """
        servicemanager.LogInfoMsg(f"[icon3-integration] FILE loop cada {self.file_interval}s")
        while self.running:
            try:
                run_results()  # tu results() en modo FILE hace una pasada y regresa
            except Exception as e:
                servicemanager.LogErrorMsg(f"[icon3-integration] Error en results() [FILE]: {e}")
            # Espera dividida en pasos cortos para reaccionar más rápido al STOP
            steps = max(1, int(self.file_interval * 2))  # pasos de 0.5s
            for _ in range(steps):
                if not self.running:
                    return
                time.sleep(0.5)


if __name__ == "__main__":
    # Comandos:
    #   python win_service.py install
    #   python win_service.py start
    #   python win_service.py stop
    #   python win_service.py remove
    #   python win_service.py debug
    win32serviceutil.HandleCommandLine(Icon3IntegrationService)
