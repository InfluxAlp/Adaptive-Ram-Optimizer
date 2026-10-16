import sys
import os
import time
import gc
import sqlite3
import datetime
import json
import uuid
import ctypes
import queue
from ctypes import wintypes
import psutil
import winreg  # Windows startup registry integration
import joblib

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QFrame, QSystemTrayIcon, QMenu,
                             QMessageBox, QDialog, QFormLayout, QDoubleSpinBox,
                             QSpinBox, QDialogButtonBox, QLineEdit, QTextEdit)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QSettings, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QFont, QFontDatabase, QColor

from model_runtime import predict_candidates
from training_worker import AutoTrainWorker
from optimizer_core import OptimizerCore

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi
REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "AdaptiveRamOptimizer"
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_SET_QUOTA = 0x0100
PROCESS_SET_INFORMATION = 0x0200
PROCESS_MEMORY_PRIORITY = 9
MemoryPriority = 2
ProcessMemoryPriority = 9
class MEMORY_PRIORITY_INFORMATION(ctypes.Structure):
    _fields_ = [("MemoryPriority", wintypes.ULONG)]

OPTIMIZATION_MODES = {
    "soft": {
        "label": "Soft", "ram_percent": 90.0, "background_sec": 180.0,
        "interval_sec": 180.0, "trim_cooldown_sec": 300.0,
    },
    "balanced": {
        "label": "Balanced", "ram_percent": 85.0, "background_sec": 60.0,
        "interval_sec": 60.0, "trim_cooldown_sec": 180.0,
    },
    "aggressive": {
        "label": "Aggressive", "ram_percent": 75.0, "background_sec": 30.0,
        "interval_sec": 20.0, "trim_cooldown_sec": 120.0,
    },
    "test": {
        "label": "Test (10% RAM)", "ram_percent": 10.0, "background_sec": 0.0,
        "interval_sec": 3.0, "trim_cooldown_sec": 15.0,
    },
}
LANGUAGE_PACKS = {
    "en": {
        "language": "Language", "english": "English", "turkish": "Turkish",
        "title": "Adaptive AI Memory Optimizer",
        "agent_collecting": "Agent status: Collecting and monitoring",
        "agent_paused": "Agent status: Data collection paused",
        "foreground": "Foreground application", "window": "Active window / page",
        "pid": "Active PID", "policy": "Optimization policy",
        "prediction": "Next application prediction", "not_enough_data": "Not enough data yet",
        "ram_usage": "RAM usage", "candidates": "AI compression candidates",
        "processes": "processes", "optimized": "Processes optimized this round",
        "reduction": "Observed RAM reduction this round", "monitored": "Active processes monitored",
        "lowered_priority": "Processes with lowered priority",
        "training_idle": "Model training: Idle (Interval: 15 min)",
        "training_background": "AI model is training in the background...",
        "training_stop": "Stop Training", "training_stopping": "Stopping training...",
        "training_again": "Train Again", "pause_collection": "Pause Data Collection",
        "resume_collection": "Resume Data Collection", "delete_data": "Delete Personal Data and Model",
        "autostart": "Start with Windows", "on": "ON", "off": "OFF", "settings": "Settings",
        "custom_profile": "Create custom profile", "delete_profile": "Delete selected custom profile",
        "custom_profiles": "Custom profiles", "profile_name": "Profile name",
        "ram_threshold": "RAM threshold (%)", "background_time": "Background time (seconds)",
        "optimization_interval": "Optimization interval (seconds)",
        "trim_cooldown": "Memory trim cooldown (seconds)",
        "dashboard": "Open Dashboard", "exit": "Exit",
        "delete_title": "Delete Telemetry Database",
        "delete_warning": "All collected telemetry data will be deleted. This cannot be undone.\n\nDo you want to continue?",
        "delete_final_title": "Final Confirmation",
        "delete_final": "FINAL CONFIRMATION: telemetry data and the trained AI model (ram_optimizer_model.pkl) will be deleted.\n\nStart from a clean slate?",
        "delete_aborted": "Delete Aborted",
        "training_not_stopped": "Training did not stop safely; no files were deleted.",
        "worker_not_stopped": "The telemetry worker did not stop safely; no files were deleted.",
        "delete_error": "The data could not be deleted completely", "delete_error_title": "Delete Error",
        "new_store": "Agent status: New personal data store ready", "files_deleted": "files deleted",
        "tray_message": "The application continues collecting personal telemetry in the background.",
        "training_error": "Training error", "model_updated": "Model updated",
        "live_telemetry": "Live Telemetry",
        "live_telemetry_title": "Live Telemetry Activity",
        "telemetry_ready": "Live telemetry view is ready.",
        "telemetry_tick": "Monitoring | Events: {events} | RAM: {ram}%",
        "optimize_now": "Optimize RAM Now",
        "optimization_complete": "Manual optimization complete: {count} processes, {memory:.2f} MB released.",
    },
    "tr": {
    "language": "Dil", "english": "İngilizce", "turkish": "Türkçe",
    "title": "Adaptif Yapay Zeka Bellek Yöneticisi",
    "agent_collecting": "Ajan durumu: Veri toplanıyor ve izleniyor",
    "agent_paused": "Ajan durumu: Veri toplama duraklatıldı",
    "foreground": "Öndeki uygulama", "window": "Aktif pencere / sayfa",
    "pid": "Aktif PID", "policy": "Optimizasyon politikası",
    "prediction": "Sonraki uygulama tahmini", "not_enough_data": "Henüz yeterli veri yok",
    "ram_usage": "RAM kullanımı", "candidates": "Yapay zeka sıkıştırma adayları",
    "processes": "süreç", "optimized": "Bu turda optimize edilen süreç",
    "reduction": "Bu turda gözlenen RAM azalması", "monitored": "İzlenen aktif süreç",
    "lowered_priority": "Önceliği Düşürülen Süreç Sayısı",
    "training_idle": "Model eğitimi: Beklemede (Aralık: 15 dk)",
    "training_background": "Yapay zeka modeli arka planda eğitiliyor...",
    "training_stop": "Eğitimi Durdur", "training_stopping": "Eğitim durduruluyor...",
    "training_again": "Tekrar Eğit", "pause_collection": "Veri Toplamayı Duraklat",
    "resume_collection": "Veri Toplamayı Başlat",
    "delete_data": "Kişisel Verileri ve Modeli Sil", "autostart": "Windows ile Başlat",
    "on": "AÇIK", "off": "KAPALI", "settings": "Ayarlar",
    "custom_profile": "Özel profil oluştur", "delete_profile": "Seçili özel profili sil",
    "custom_profiles": "Özel profiller", "profile_name": "Profil adı",
    "ram_threshold": "RAM eşiği (%)", "background_time": "Arka plan süresi (saniye)",
    "optimization_interval": "Optimizasyon aralığı (saniye)",
    "trim_cooldown": "Bellek temizleme cooldown süresi (saniye)",
    "dashboard": "Paneli Aç", "exit": "Çıkış",
    "delete_title": "Telemetry Veritabanını Sil",
    "delete_warning": "Toplanan tüm telemetry verileri silinecek. Bu işlem geri alınamaz.\n\nDevam etmek istiyor musun?",
    "delete_final_title": "Son Onay",
    "delete_final": "SON ONAY: telemetry verileri ve eğitilmiş yapay zeka modeli (ram_optimizer_model.pkl) silinecek.\n\nSıfırdan başlamak için hepsi silinsin mi?",
    "delete_aborted": "Silme Durduruldu",
    "training_not_stopped": "Eğitim güvenli şekilde durmadı; hiçbir dosya silinmedi.",
    "worker_not_stopped": "Telemetry worker güvenli şekilde durmadı; hiçbir dosya silinmedi.",
    "delete_error": "Veriler tamamen silinemedi", "delete_error_title": "Silme Hatası",
    "new_store": "Ajan durumu: Yeni kişisel veri alanı hazır",
    "files_deleted": "dosya silindi",
    "tray_message": "Uygulama arka planda kişisel telemetry toplamaya devam ediyor.",
    "training_error": "Eğitim hatası", "model_updated": "Model güncellendi",
    "live_telemetry": "Canlı Telemetri",
    "live_telemetry_title": "Canlı Telemetri İşlemleri",
    "telemetry_ready": "Canlı telemetri görünümü hazır.",
    "telemetry_tick": "İzleme | Olay: {events} | RAM: %{ram}",
    "optimize_now": "RAM'i Şimdi Optimize Et",
    "optimization_complete": "Manuel optimizasyon tamamlandı: {count} süreç, {memory:.2f} MB RAM azaltıldı.",
}
}
PROTECTED_PROCESS_NAMES = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "svchost.exe", "dwm.exe", "explorer.exe",
    "adaptive_ram_optimizer.exe"
}
MODEL_CONFIDENCE_THRESHOLD = 0.80
HIGH_PRIORITY_SCORE_THRESHOLD = 65.0
HIGH_PRIORITY_MIN_FOREGROUND_SECONDS = 60.0
MIN_BACKGROUND_SECONDS = 30.0
MIN_WORKING_SET_MB = 30.0
MIN_SYSTEM_RAM_PERCENT = 85.0
TRIM_COOLDOWN_SECONDS = 180.0
FOREGROUND_PROCESS_MIN_INTERVAL_SEC = 2.0


def get_app_data_dir():
    """Return a writable user data directory independent of the EXE location."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    base_dir = local_app_data or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    data_dir = os.path.join(base_dir, "AdaptiveRamOptimizer")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except OSError:
        data_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    return data_dir

kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
psapi.EmptyWorkingSet.restype = wintypes.BOOL
kernel32.SetProcessWorkingSetSize.argtypes = [
    wintypes.HANDLE, ctypes.c_size_t, ctypes.c_size_t
]
kernel32.SetProcessWorkingSetSize.restype = wintypes.BOOL
kernel32.SetProcessInformation.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
]
kernel32.SetProcessInformation.restype = wintypes.BOOL


def trim_process_memory(pid):
    """Trim a process working set and return the observed RSS reduction in MB."""
    if os.name != "nt" or not pid:
        return None

    try:
        process = psutil.Process(int(pid))
        if int(pid) != os.getpid() and process.name().lower() in PROTECTED_PROCESS_NAMES:
            return None
        before_mb = process.memory_info().rss / (1024 * 1024)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error, ValueError, TypeError):
        return None

    handle = kernel32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA, False, int(pid)
    )
    if not handle:
        return None
    try:
        memory_priority = MEMORY_PRIORITY_INFORMATION(MemoryPriority)
        kernel32.SetProcessInformation(
            handle, PROCESS_MEMORY_PRIORITY, ctypes.byref(memory_priority), ctypes.sizeof(memory_priority)
        )
        success = bool(psapi.EmptyWorkingSet(handle))
        if not success:
            empty_size = ctypes.c_size_t(-1).value
            success = bool(kernel32.SetProcessWorkingSetSize(handle, empty_size, empty_size))
        if not success:
            return None

        try:
            after_mb = psutil.Process(int(pid)).memory_info().rss / (1024 * 1024)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
            return 0.0
        return max(0.0, round(before_mb - after_mb, 2))
    finally:
        kernel32.CloseHandle(handle)


def _process_name(pid):
    try:
        return psutil.Process(int(pid)).name().lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error, ValueError, TypeError):
        return ""


def set_process_priorities(
    pid,
    is_foreground=False,
    is_candidate=False,
    is_high_priority=False,
):
    """Apply the least intrusive priority policy allowed by the process state."""
    if not pid or int(pid) == os.getpid() or _process_name(pid) in PROTECTED_PROCESS_NAMES:
        return False
    try:
        process = psutil.Process(int(pid))
        if is_high_priority:
            process.nice(psutil.HIGH_PRIORITY_CLASS)
            return True
        if is_foreground:
            process.nice(psutil.NORMAL_PRIORITY_CLASS)
            return True
        if not is_candidate:
            return False

        process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        try:
            process.ionice(psutil.IOPRIORITY_LOW)
        except (AttributeError, psutil.AccessDenied, psutil.NoSuchProcess, psutil.Error):
            pass
        handle = kernel32.OpenProcess(PROCESS_SET_INFORMATION, False, int(pid))
        if not handle:
            return True
        try:
            memory_priority = MEMORY_PRIORITY_INFORMATION(MemoryPriority)
            kernel32.SetProcessInformation(
                handle,
                ProcessMemoryPriority,
                ctypes.byref(memory_priority),
                ctypes.sizeof(memory_priority),
            )
        finally:
            kernel32.CloseHandle(handle)
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error, ValueError, TypeError):
        return False


def calculate_foreground_priority_score(foreground_seconds, background_seconds, cpu_percent):
    total_seconds = foreground_seconds + background_seconds
    focus_ratio = foreground_seconds / total_seconds if total_seconds > 0 else 0.0
    focus_score = focus_ratio * 60.0
    duration_score = min(foreground_seconds / 600.0, 1.0) * 25.0
    activity_score = min(max(cpu_percent, 0.0) / 100.0, 1.0) * 15.0
    return round(focus_score + duration_score + activity_score, 2)


def set_autostart(enable=True):
    """Add or remove the application from Windows startup."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_ALL_ACCESS)
        if enable:
            script_path = os.path.abspath(sys.argv[0])
            startup_command = (
                f'"{sys.executable}" "{script_path}"'
                if script_path.lower().endswith(".py") else f'"{script_path}"'
            )
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, startup_command)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"Registry error: {e}")
        return False

def is_autostart_enabled():
    """Return whether the application is registered for Windows startup."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False

class EventDrivenTelemetryWorker(QThread):
    """Persist foreground events without periodic process or window polling."""

    data_updated = pyqtSignal(dict)
    telemetry_log = pyqtSignal(str)
    manual_optimization_finished = pyqtSignal(int, float)

    def __init__(self, db_path="ml_dataset_telemetry.db", model_path="ram_optimizer_model.pkl"):
        super().__init__()
        self.db_path = db_path
        self.model_path = model_path
        self.collection_paused = False
        self.optimization_mode = "balanced"
        self.model = None
        self._events = queue.Queue()
        self._stop_requested = False
        self._core = None
        self._last_event_ms = None
        self._last_processed_at = 0.0
        self._last_processed_process = None
        self._accumulators = {}
        self._last_trim_times = {}
        self._last_optimization_at = 0.0
        self._lowered_priority_pids = set()
        self._event_count = 0
        self.load_ml_model()

    def load_ml_model(self):
        self.model = None
        if os.path.exists(self.model_path):
            try:
                self.model = joblib.load(self.model_path)
            except (OSError, ValueError, EOFError, AttributeError):
                self.model = None

    def set_optimization_mode(self, mode):
        if mode in OPTIMIZATION_MODES:
            self.optimization_mode = mode

    def set_collection_paused(self, paused):
        self.collection_paused = paused

    def pause_collection(self):
        self.set_collection_paused(True)

    def resume_collection(self):
        self.set_collection_paused(False)

    def stop(self):
        self._stop_requested = True
        self._events.put(None)

    def optimize_now(self):
        """Queue an immediate optimization request for the worker thread."""
        self._events.put(("manual_optimization",))

    def _run_manual_optimization(self):
        optimized_count = 0
        released_memory_mb = 0.0

        foreground_pid = 0
        try:
            foreground_window = user32.GetForegroundWindow()
            foreground_pid_value = wintypes.DWORD()
            user32.GetWindowThreadProcessId(
                foreground_window, ctypes.byref(foreground_pid_value)
            )
            foreground_pid = foreground_pid_value.value
        except (AttributeError, OSError):
            pass

        for process in psutil.process_iter(["pid", "name", "memory_info"]):
            try:
                pid = int(process.info["pid"])
                name = (process.info["name"] or "").lower()
                if (
                    pid == os.getpid()
                    or pid == foreground_pid
                    or name in PROTECTED_PROCESS_NAMES
                ):
                    continue
                memory_info = process.info["memory_info"]
                if memory_info is None or memory_info.rss < MIN_WORKING_SET_MB * 1024 * 1024:
                    continue

                reduction = trim_process_memory(pid)
                priority_changed = set_process_priorities(pid, is_candidate=True)
                if reduction is not None or priority_changed:
                    optimized_count += 1
                if reduction is not None:
                    released_memory_mb += reduction
                    self._last_trim_times[pid] = time.monotonic()
                if priority_changed:
                    self._lowered_priority_pids.add(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error, KeyError, TypeError):
                continue

        released_memory_mb = round(released_memory_mb, 2)
        self._log(
            f"Manuel optimizasyon: {optimized_count} süreç işlendi, "
            f"{released_memory_mb:.2f} MB RAM azaltıldı."
        )
        self.manual_optimization_finished.emit(optimized_count, released_memory_mb)

    def _log(self, message):
        self.telemetry_log.emit(message)

    def _init_db(self, connection):
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS foreground_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                pid INTEGER, process_name TEXT NOT NULL, window_title TEXT,
                started_at TEXT NOT NULL, ended_at TEXT, duration_sec REAL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS app_transitions (
                transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_process TEXT NOT NULL, to_process TEXT NOT NULL,
                hour INTEGER NOT NULL, weekday INTEGER NOT NULL, occurred_at TEXT NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS event_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL, pid INTEGER NOT NULL,
                process_name TEXT NOT NULL, window_title TEXT,
                previous_focus_duration_ms INTEGER NOT NULL
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS system_snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL, hour INTEGER NOT NULL,
                day_of_week INTEGER NOT NULL, is_weekend INTEGER NOT NULL,
                total_cpu_percent REAL NOT NULL, used_ram_mb REAL NOT NULL,
                free_ram_mb REAL NOT NULL, ram_percent REAL NOT NULL,
                active_pid INTEGER, active_process_name TEXT,
                active_window_title TEXT
            )
        """)
        connection.execute("""
            CREATE TABLE IF NOT EXISTS process_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT, snapshot_id INTEGER,
                pid INTEGER NOT NULL, process_name TEXT NOT NULL,
                is_foreground INTEGER NOT NULL, working_set_mb REAL NOT NULL,
                commit_size_mb REAL NOT NULL, cpu_percent REAL,
                thread_count INTEGER, handle_count INTEGER,
                read_bytes_sec REAL, write_bytes_sec REAL,
                accumulated_fg_sec REAL DEFAULT 0,
                accumulated_bg_sec REAL DEFAULT 0
            )
        """)
        connection.commit()

    @staticmethod
    def _predict_next(connection, process_name, hour):
        row = connection.execute(
            "SELECT to_process FROM app_transitions "
            "WHERE from_process=? AND hour=? "
            "GROUP BY to_process ORDER BY COUNT(*) DESC LIMIT 1",
            (process_name, hour),
        ).fetchone()
        return row[0] if row else "Not enough data yet"

    def run(self):
        connection = sqlite3.connect(self.db_path)
        self._init_db(connection)
        previous_name = None
        session_id = None
        try:
            self._core = OptimizerCore()
            self._core.start(self._events.put)
            while not self._stop_requested:
                event = self._events.get()
                if event is None:
                    break
                if isinstance(event, tuple) and event[0] == "manual_optimization":
                    self._run_manual_optimization()
                    continue
                if self.collection_paused:
                    continue
                self._event_count += 1

                process_name = event.process_name or "Unknown"
                title = event.window_title
                now_monotonic = time.monotonic()
                if (
                    process_name == self._last_processed_process
                    and now_monotonic - self._last_processed_at
                    < FOREGROUND_PROCESS_MIN_INTERVAL_SEC
                ):
                    continue
                self._last_processed_process = process_name
                self._last_processed_at = now_monotonic
                self._log(f"Odak olayı işlendi: {process_name} (PID {event.process_id})")
                timestamp = datetime.datetime.fromtimestamp(
                    event.timestamp / 1000, datetime.timezone.utc
                ).astimezone()
                timestamp_text = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                if session_id is not None:
                    connection.execute(
                        "UPDATE foreground_sessions SET ended_at=?, duration_sec=? "
                        "WHERE session_id=?",
                        (timestamp_text, event.previous_focus_duration_ms / 1000, session_id),
                    )
                if previous_name and previous_name != process_name:
                    connection.execute(
                        "INSERT INTO app_transitions "
                        "(from_process,to_process,hour,weekday,occurred_at) VALUES (?,?,?,?,?)",
                        (previous_name, process_name, timestamp.hour,
                         timestamp.weekday(), timestamp_text),
                    )
                cursor = connection.execute(
                    "INSERT INTO foreground_sessions "
                    "(pid,process_name,window_title,started_at) VALUES (?,?,?,?)",
                    (event.process_id, process_name, title, timestamp_text),
                )
                session_id = cursor.lastrowid
                connection.execute(
                    "INSERT INTO event_telemetry "
                    "(timestamp,pid,process_name,window_title,previous_focus_duration_ms) "
                    "VALUES (?,?,?,?,?)",
                    (event.timestamp, event.process_id, process_name, title,
                     event.previous_focus_duration_ms),
                )
                connection.commit()
                self._log("Odak ve geçiş telemetrisi kaydedildi.")
                previous_name = process_name
                predicted_next = self._predict_next(
                    connection, process_name, timestamp.hour
                )

                system_memory = psutil.virtual_memory()
                elapsed_sec = (
                    event.previous_focus_duration_ms / 1000
                    if self._last_event_ms is not None
                    else 0.0
                )
                self._last_event_ms = event.timestamp
                now_text = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                snapshot = connection.execute(
                    "INSERT INTO system_snapshots "
                    "(timestamp,hour,day_of_week,is_weekend,total_cpu_percent,"
                    "used_ram_mb,free_ram_mb,ram_percent,active_pid,"
                    "active_process_name,active_window_title) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        now_text, timestamp.hour, timestamp.weekday(),
                        int(timestamp.weekday() >= 5), psutil.cpu_percent(None),
                        round((system_memory.total - system_memory.available) / (1024 * 1024), 2),
                        round(system_memory.available / (1024 * 1024), 2),
                        system_memory.percent, event.process_id, process_name, title,
                    ),
                )
                snapshot_id = snapshot.lastrowid
                candidates_count = 0
                optimized_count = 0
                released_memory_mb = 0.0
                model_rows = []
                process_count = 0
                for process in psutil.process_iter([
                    "pid", "name", "memory_info", "num_threads",
                    "num_handles", "cpu_percent",
                ]):
                    try:
                        info = process.info
                        pid = int(info["pid"])
                        name = info["name"] or "Unknown"
                        memory = info["memory_info"]
                        working_set_mb = round(memory.rss / (1024 * 1024), 2)
                        commit_size_mb = round(memory.vms / (1024 * 1024), 2)
                        state = self._accumulators.setdefault(
                            pid, {"fg_sec": 0.0, "bg_sec": 0.0}
                        )
                        if pid == event.process_id:
                            state["fg_sec"] += elapsed_sec
                        else:
                            state["bg_sec"] += elapsed_sec
                        fg_sec = state["fg_sec"]
                        bg_sec = state["bg_sec"]
                        process_count += 1
                        cpu_percent = info["cpu_percent"] or 0.0
                        threads = info["num_threads"] or 0
                        handles = info["num_handles"] or 0
                        focus_ratio = fg_sec / (fg_sec + bg_sec) if fg_sec + bg_sec else 0.0
                        row = (
                            pid, timestamp.hour, int(timestamp.weekday() >= 5),
                            working_set_mb, commit_size_mb, cpu_percent, threads,
                            handles, fg_sec, bg_sec, focus_ratio, system_memory.percent,
                        )
                        model_rows.append(row)
                        connection.execute(
                            "INSERT INTO process_telemetry "
                            "(snapshot_id,pid,process_name,is_foreground,working_set_mb,"
                            "commit_size_mb,cpu_percent,thread_count,handle_count,"
                            "read_bytes_sec,write_bytes_sec,accumulated_fg_sec,"
                            "accumulated_bg_sec) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (snapshot_id, pid, name, int(pid == event.process_id),
                             working_set_mb, commit_size_mb, cpu_percent, threads,
                             handles, 0.0, 0.0, fg_sec, bg_sec),
                        )
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
                        continue

                self._log(f"{process_count} süreç tarandı; AI adayları hesaplanıyor.")
                predictions = predict_candidates(self.model, model_rows)
                mode = OPTIMIZATION_MODES.get(
                    self.optimization_mode, OPTIMIZATION_MODES["balanced"]
                )
                for pid, prediction in predictions.items():
                    if prediction.get("prediction") == 1 and prediction.get("confidence", 0.0) >= MODEL_CONFIDENCE_THRESHOLD:
                        candidates_count += 1
                now_monotonic = time.monotonic()
                trim_cooldown_sec = mode.get(
                    "trim_cooldown_sec", TRIM_COOLDOWN_SECONDS
                )
                optimization_due = (
                    now_monotonic - self._last_optimization_at >= mode["interval_sec"]
                )
                if optimization_due:
                    self._log("Optimizasyon koşulları kontrol ediliyor.")
                    for pid, state in list(self._accumulators.items()):
                        if pid == event.process_id or _process_name(pid) in PROTECTED_PROCESS_NAMES:
                            continue
                        if (
                            state["bg_sec"] < mode["background_sec"]
                            or system_memory.percent < mode["ram_percent"]
                        ):
                            continue
                        prediction = predictions.get(pid, {})
                        if self.model is not None and (
                            prediction.get("prediction") != 1
                            or prediction.get("confidence", 0.0) < MODEL_CONFIDENCE_THRESHOLD
                        ):
                            continue
                        if self.model is None and state["bg_sec"] < max(
                            mode["background_sec"], MIN_BACKGROUND_SECONDS
                        ):
                            continue
                        if (
                            now_monotonic - self._last_trim_times.get(pid, 0.0)
                            < trim_cooldown_sec
                        ):
                            continue
                        reduction = trim_process_memory(pid)
                        if reduction is not None:
                            optimized_count += 1
                            released_memory_mb += reduction
                            self._last_trim_times[pid] = now_monotonic
                            self._log(
                                f"Bellek temizlendi: PID {pid}, "
                                f"{reduction:.2f} MB azaltıldı."
                            )
                        if (
                            pid not in self._lowered_priority_pids
                            and set_process_priorities(pid, is_candidate=True)
                        ):
                            self._lowered_priority_pids.add(pid)
                            self._log(f"Öncelik düşürüldü: PID {pid}")
                    self._last_optimization_at = now_monotonic
                connection.commit()
                self.data_updated.emit({
                    "fg_name": process_name,
                    "fg_title": title,
                    "active_pid": event.process_id,
                    "ram_percent": system_memory.percent,
                    "used_ram_mb": round(
                        (system_memory.total - system_memory.available) / (1024 * 1024), 2
                    ),
                    "candidates_count": candidates_count,
                    "optimized_count": optimized_count,
                    "released_memory_mb": released_memory_mb,
                    "process_count": process_count,
                    "lowered_priority_count": len(self._lowered_priority_pids),
                    "telemetry_count": self._event_count,
                    "predicted_next": (
                        predicted_next
                    ),
                })
        except OSError as error:
            print(f"Event-driven telemetry core unavailable: {error}")
        finally:
            if self._core is not None:
                self._core.stop()
                self._core = None
            connection.close()


class RamOptimizerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        data_dir = get_app_data_dir()
        self.db_path = os.path.join(data_dir, "ml_dataset_telemetry.db")
        self.model_path = os.path.join(data_dir, "ram_optimizer_model.pkl")
        self.language = "en"
        self.load_custom_profiles()
        settings = QSettings("AdaptiveRamOptimizer", "AdaptiveRamOptimizer")
        saved_mode = str(settings.value("optimization_mode", "balanced"))
        self.optimization_mode = (
            saved_mode if saved_mode in OPTIMIZATION_MODES else "balanced"
        )
        if saved_mode not in OPTIMIZATION_MODES:
            saved_label = str(settings.value("optimization_profile_label", ""))
            for profile_id, profile in self.custom_profiles.items():
                if profile.get("label") == saved_label:
                    self.optimization_mode = profile_id
                    break
        self.init_ui()
        if not is_autostart_enabled():
            set_autostart(True)
        
        # Start the telemetry worker.
        self.worker = EventDrivenTelemetryWorker(db_path=self.db_path, model_path=self.model_path)
        self.worker.set_optimization_mode(self.optimization_mode)
        self.worker.data_updated.connect(self.update_dashboard)
        self.worker.manual_optimization_finished.connect(self.on_manual_optimization_finished)
        self.worker.start()

        # Check for automatic retraining every 15 minutes.
        self.last_train_time = time.time()
        self.retrain_interval_sec = 900
        self.retrain_worker = None
        self.telemetry_dialog = None
        self.telemetry_log_view = None
        self.telemetry_timer = None
        self.apply_language()

        # Start the first background training run.
        self.trigger_retrain()

    def t(self, key):
        return LANGUAGE_PACKS[self.language][key]

    def load_custom_profiles(self):
        settings = QSettings("AdaptiveRamOptimizer", "AdaptiveRamOptimizer")
        self.custom_profiles = {}
        raw_profiles = settings.value("custom_profiles", "[]")
        try:
            saved_profiles = json.loads(str(raw_profiles))
        except (TypeError, ValueError, json.JSONDecodeError):
            saved_profiles = []
        if not saved_profiles:
            legacy_label = settings.value("custom_profile/label", "")
            if legacy_label:
                saved_profiles = [{
                    "label": str(legacy_label),
                    "ram_percent": float(settings.value("custom_profile/ram_percent", 85.0)),
                    "background_sec": float(settings.value("custom_profile/background_sec", 60.0)),
                    "interval_sec": float(settings.value("custom_profile/interval_sec", 60.0)),
                    "trim_cooldown_sec": float(
                        settings.value("custom_profile/trim_cooldown_sec", 180.0)
                    ),
                }]
        for profile in saved_profiles:
            profile_id = f"custom_{uuid.uuid4().hex}"
            self.custom_profiles[profile_id] = profile
            OPTIMIZATION_MODES[profile_id] = profile

    def save_custom_profiles(self):
        settings = QSettings("AdaptiveRamOptimizer", "AdaptiveRamOptimizer")
        settings.setValue("custom_profiles", json.dumps(list(self.custom_profiles.values())))

    def create_custom_profile(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.t("custom_profile"))
        form = QFormLayout(dialog)

        name_input = QLineEdit()
        ram_input = QDoubleSpinBox()
        ram_input.setRange(1.0, 99.0)
        ram_input.setValue(85.0)
        background_input = QSpinBox()
        background_input.setRange(0, 86400)
        background_input.setValue(60)
        interval_input = QSpinBox()
        interval_input.setRange(3, 86400)
        interval_input.setValue(60)
        cooldown_input = QSpinBox()
        cooldown_input.setRange(15, 86400)
        cooldown_input.setValue(180)

        form.addRow(self.t("profile_name"), name_input)
        form.addRow(self.t("ram_threshold"), ram_input)
        form.addRow(self.t("background_time"), background_input)
        form.addRow(self.t("optimization_interval"), interval_input)
        form.addRow(self.t("trim_cooldown"), cooldown_input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        label = name_input.text().strip() or "Custom"
        profile_id = f"custom_{uuid.uuid4().hex}"
        profile = {
            "label": label,
            "ram_percent": ram_input.value(),
            "background_sec": float(background_input.value()),
            "interval_sec": float(interval_input.value()),
            "trim_cooldown_sec": float(cooldown_input.value()),
        }
        self.custom_profiles[profile_id] = profile
        OPTIMIZATION_MODES[profile_id] = profile
        self.save_custom_profiles()
        self.add_profile_action(profile_id, profile)
        self.set_optimization_mode(profile_id)

    def add_profile_action(self, profile_id, profile):
        action = QAction(profile["label"], self)
        action.setCheckable(True)
        action.triggered.connect(
            lambda checked, selected_mode=profile_id:
            self.set_optimization_mode(selected_mode)
        )
        self.profile_actions[profile_id] = action
        self.profile_menu.addAction(action)

    def delete_custom_profile(self):
        profile_id = self.optimization_mode
        if profile_id not in self.custom_profiles:
            return
        profile = self.custom_profiles[profile_id]
        answer = QMessageBox.question(
            self,
            self.t("delete_profile"),
            f"{profile['label']}\n\n"
            + (
                "Delete this profile?"
                if self.language == "en"
                else "Bu profil silinsin mi?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        action = self.profile_actions.pop(profile_id, None)
        if action is not None:
            self.profile_menu.removeAction(action)
            action.deleteLater()
        self.custom_profiles.pop(profile_id, None)
        OPTIMIZATION_MODES.pop(profile_id, None)
        self.save_custom_profiles()
        self.set_optimization_mode("balanced")

    def set_language(self, language):
        if language in LANGUAGE_PACKS:
            self.language = language
            self.apply_language()

    def apply_language(self):
        self.setWindowTitle(self.t("title"))
        self.lbl_status.setText(
            self.t("agent_paused") if self.worker.collection_paused else self.t("agent_collecting")
        )
        self.lbl_focus.setText(f"{self.t('foreground')}: -")
        self.lbl_window.setText(f"{self.t('window')}: -")
        self.lbl_pid.setText(f"{self.t('pid')}: -")
        self.lbl_mode.setText(
            f"{self.t('policy')}: {OPTIMIZATION_MODES[self.optimization_mode]['label']}"
        )
        self.lbl_prediction.setText(f"{self.t('prediction')}: {self.t('not_enough_data')}")
        self.lbl_ram.setText(f"{self.t('ram_usage')}: 0% (0 MB)")
        self.lbl_ai_candidates.setText(f"{self.t('candidates')}: 0 {self.t('processes')}")
        self.lbl_optimized.setText(f"{self.t('optimized')}: 0")
        self.lbl_released_memory.setText(f"{self.t('reduction')}: 0 MB")
        self.lbl_process_count.setText(f"{self.t('monitored')}: 0")
        self.lbl_lowered_priority.setText(f"{self.t('lowered_priority')}: 0")
        training_running = self.retrain_worker is not None and self.retrain_worker.isRunning()
        self.lbl_train_status.setText(
            self.t("training_background") if training_running else self.t("training_idle")
        )
        self.btn_train.setText(
            self.t("training_stop") if training_running
            else self.t("training_again")
        )
        self.btn_collection.setText(
            self.t("resume_collection") if self.worker.collection_paused else self.t("pause_collection")
        )
        self.btn_optimize_now.setText(self.t("optimize_now"))
        self.btn_live_telemetry.setText(self.t("live_telemetry"))
        self.btn_delete_database.setText(self.t("delete_data"))
        autostart_state = self.t("on") if is_autostart_enabled() else self.t("off")
        self.btn_autostart.setText(f"{self.t('autostart')}: {autostart_state}")
        self.btn_settings.setText(
            f"{self.t('settings')}: {OPTIMIZATION_MODES[self.optimization_mode]['label']}"
        )
        language_label_key = "english" if self.language == "en" else "turkish"
        self.language_menu.setTitle(f"{self.t('language')}: {self.t(language_label_key)}")
        self.language_actions["en"].setText(self.t("english"))
        self.language_actions["tr"].setText(self.t("turkish"))
        self.custom_profile_action.setText(self.t("custom_profile"))
        self.delete_profile_action.setText(self.t("delete_profile"))
        self.show_action.setText(self.t("dashboard"))
        self.quit_action.setText(self.t("exit"))

    def localize_training_status(self, status_msg):
        if status_msg.startswith("Training stopped"):
            return self.t("training_stopping")
        if status_msg.startswith("Not enough data"):
            return self.t("not_enough_data")
        if status_msg.startswith("Training error"):
            prefix = self.t("training_error") if self.language == "tr" else "Training error"
            return status_msg.replace("Training error", prefix, 1)
        if status_msg.startswith("Model updated"):
            prefix = self.t("model_updated") if self.language == "tr" else "Model updated"
            return status_msg.replace("Model updated", prefix, 1)
        return status_msg

    def trigger_retrain(self):
        if self.retrain_worker is not None and self.retrain_worker.isRunning():
            return
        self.lbl_train_status.setText(self.t("training_background"))
        self.btn_train.setText(self.t("training_stop"))
        self.retrain_worker = AutoTrainWorker(
            db_path=self.db_path,
            model_path=self.model_path,
            cleanup_callback=trim_process_memory,
        )
        self.retrain_worker.training_finished.connect(self.on_retrain_finished)
        self.retrain_worker.start()

    def toggle_training(self):
        if self.retrain_worker is not None and self.retrain_worker.isRunning():
            self.stop_training()
        else:
            self.trigger_retrain()

    def stop_training(self):
        if self.retrain_worker is None or not self.retrain_worker.isRunning():
            return
        self.retrain_worker.request_stop()
        self.lbl_train_status.setText(self.t("training_stopping"))

    def on_retrain_finished(self, status_msg):
        self.lbl_train_status.setText(self.localize_training_status(status_msg))
        self.btn_train.setText(self.t("training_again"))
        # Reload the newly trained model in the live worker.
        self.worker.load_ml_model()

    def set_optimization_mode(self, mode):
        if mode not in OPTIMIZATION_MODES:
            return
        self.optimization_mode = mode
        settings = QSettings("AdaptiveRamOptimizer", "AdaptiveRamOptimizer")
        settings.setValue("optimization_mode", mode)
        settings.setValue(
            "optimization_profile_label",
            OPTIMIZATION_MODES[mode].get("label", ""),
        )
        self.worker.set_optimization_mode(mode)
        config = OPTIMIZATION_MODES[mode]
        self.btn_settings.setText(f"{self.t('settings')}: {config['label']}")
        self.lbl_mode.setText(f"{self.t('policy')}: {config['label']}")

    def toggle_collection(self):
        paused = not self.worker.collection_paused
        self.worker.set_collection_paused(paused)
        if paused:
            self.btn_collection.setText(self.t("resume_collection"))
            self.lbl_status.setText(self.t("agent_paused"))
            self.lbl_status.setStyleSheet("color: #f9e2af; font-weight: bold;")
        else:
            self.btn_collection.setText(self.t("pause_collection"))
            self.lbl_status.setText(self.t("agent_collecting"))
            self.lbl_status.setStyleSheet("color: #a6e3a1; font-weight: bold;")

    def optimize_now(self):
        self.btn_optimize_now.setEnabled(False)
        self.worker.optimize_now()

    def on_manual_optimization_finished(self, count, released_memory_mb):
        self.btn_optimize_now.setEnabled(True)
        self.lbl_status.setText(
            self.t("optimization_complete").format(
                count=count, memory=released_memory_mb
            )
        )
        self.lbl_status.setStyleSheet("color: #a6e3a1; font-weight: bold;")

    def delete_database(self):
        first_confirmation = QMessageBox.warning(
            self,
            self.t("delete_title"),
            self.t("delete_warning"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if first_confirmation != QMessageBox.StandardButton.Yes:
            return

        second_confirmation = QMessageBox.question(
            self,
            self.t("delete_final_title"),
            self.t("delete_final"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if second_confirmation != QMessageBox.StandardButton.Yes:
            return

        if self.retrain_worker is not None and self.retrain_worker.isRunning():
            self.retrain_worker.request_stop()
            if not self.retrain_worker.wait(10000):
                QMessageBox.critical(self, self.t("delete_aborted"), self.t("training_not_stopped"))
                return

        self.worker.stop()
        if not self.worker.wait(10000):
            QMessageBox.critical(self, self.t("delete_aborted"), self.t("worker_not_stopped"))
            return

        deleted_files = 0
        try:
            for data_file in (
                self.db_path,
                f"{self.db_path}-wal",
                f"{self.db_path}-shm",
                self.model_path,
            ):
                if os.path.exists(data_file):
                    os.remove(data_file)
                    deleted_files += 1
        except OSError as error:
            QMessageBox.critical(
                self, self.t("delete_error_title"), f"{self.t('delete_error')}:\n{error}"
            )
            return

        self.worker = EventDrivenTelemetryWorker(db_path=self.db_path, model_path=self.model_path)
        self.worker.set_optimization_mode(self.optimization_mode)
        self.worker.data_updated.connect(self.update_dashboard)
        self.worker.manual_optimization_finished.connect(self.on_manual_optimization_finished)
        self.worker.start()
        self.btn_collection.setText(self.t("pause_collection"))
        self.lbl_status.setText(f"{self.t('new_store')} ({deleted_files} {self.t('files_deleted')})")
        self.lbl_status.setStyleSheet("color: #a6e3a1; font-weight: bold;")

    def init_ui(self):
        self.setWindowTitle(self.t("title"))
        self.setFixedSize(620, 680)

        font_path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeui.ttf")
        font_id = QFontDatabase.addApplicationFont(font_path)
        font_families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        font_family = font_families[0] if font_families else "Segoe UI"
        QApplication.instance().setFont(QFont(font_family, 9))
        
        self.setStyleSheet("""
            QMainWindow { background-color: #10141c; }
            QLabel {
                color: #d7dee9;
                background-color: transparent;
                font-size: 9pt;
            }
            QFrame, QWidget#infoCard {
                background-color: #1b2330;
                border: 1px solid #2b3747;
                border-radius: 8px;
            }
            QPushButton {
                background-color: #4f8cc9; color: #f7fbff; font-weight: 600;
                border: 0; border-radius: 4px; padding: 3px 8px;
                min-height: 22px; font-size: 8.5pt;
            }
            QPushButton:hover { background-color: #65a2df; }
            QPushButton:disabled { background-color: #344253; color: #93a0af; }
            QPushButton#autostartActive { background-color: #3d9b78; }
            QPushButton#dangerButton { background-color: #a84b59; }
            QPushButton#dangerButton:hover { background-color: #c46170; }
            QMenu { background-color: #1b2330; color: #d7dee9; border: 1px solid #344253; }
            QMenu::item:selected { background-color: #315d86; }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(4)

        # Header.
        title_label = QLabel(self.t("title"))
        title_label.setFont(QFont(font_family, 13, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        # Card 1: live status and foreground process.
        frame1 = QWidget()
        frame1.setObjectName("infoCard")
        layout1 = QVBoxLayout(frame1)
        layout1.setContentsMargins(10, 8, 10, 8)
        layout1.setSpacing(3)
        self.lbl_status = QLabel("Agent status: Collecting and monitoring")
        self.lbl_status.setStyleSheet("color: #a6e3a1; font-weight: bold;")
        self.lbl_focus = QLabel("Foreground application: -")
        self.lbl_window = QLabel("Active window / page: -")
        self.lbl_pid = QLabel("Active PID: -")
        self.lbl_mode = QLabel("Optimization policy: Balanced")
        self.lbl_prediction = QLabel("Next application prediction: Not enough data yet")
        for label in (self.lbl_status, self.lbl_focus, self.lbl_window, self.lbl_pid,
                      self.lbl_mode, self.lbl_prediction):
            label.setMinimumHeight(18)
            label.setWordWrap(True)
            label.raise_()
        layout1.addWidget(self.lbl_status)
        layout1.addWidget(self.lbl_focus)
        layout1.addWidget(self.lbl_window)
        layout1.addWidget(self.lbl_pid)
        layout1.addWidget(self.lbl_mode)
        layout1.addWidget(self.lbl_prediction)
        main_layout.addWidget(frame1)

        # Card 2: system status and AI candidates.
        frame2 = QWidget()
        frame2.setObjectName("infoCard")
        layout2 = QVBoxLayout(frame2)
        layout2.setContentsMargins(10, 8, 10, 8)
        layout2.setSpacing(3)
        self.lbl_ram = QLabel("RAM usage: 0% (0 MB)")
        self.lbl_ai_candidates = QLabel("AI compression candidates: 0 processes")
        self.lbl_ai_candidates.setStyleSheet("color: #f9e2af; font-weight: bold;")
        self.lbl_optimized = QLabel("Processes optimized this round: 0")
        self.lbl_released_memory = QLabel("Observed RAM reduction this round: 0 MB")
        self.lbl_process_count = QLabel("Active processes monitored: 0")
        self.lbl_lowered_priority = QLabel("Processes with lowered priority: 0")
        for label in (self.lbl_ram, self.lbl_ai_candidates, self.lbl_optimized,
                      self.lbl_released_memory, self.lbl_process_count,
                      self.lbl_lowered_priority):
            label.setMinimumHeight(18)
            label.raise_()
        layout2.addWidget(self.lbl_ram)
        layout2.addWidget(self.lbl_ai_candidates)
        layout2.addWidget(self.lbl_optimized)
        layout2.addWidget(self.lbl_released_memory)
        layout2.addWidget(self.lbl_process_count)
        layout2.addWidget(self.lbl_lowered_priority)
        main_layout.addWidget(frame2)

        # Card 3: automatic training status.
        frame3 = QFrame()
        layout3 = QVBoxLayout(frame3)
        layout3.setContentsMargins(10, 8, 10, 8)
        layout3.setSpacing(4)
        self.lbl_train_status = QLabel("Model training: Idle (Interval: 15 min)")
        self.lbl_train_status.setFont(QFont(font_family, 9))
        self.btn_train = QPushButton("Train Again")
        self.btn_train.clicked.connect(self.toggle_training)
        layout3.addWidget(self.lbl_train_status)
        layout3.addWidget(self.btn_train)
        main_layout.addWidget(frame3)

        self.btn_collection = QPushButton("Pause Data Collection")
        self.btn_collection.clicked.connect(self.toggle_collection)
        main_layout.addWidget(self.btn_collection)

        self.btn_optimize_now = QPushButton(self.t("optimize_now"))
        self.btn_optimize_now.clicked.connect(self.optimize_now)
        main_layout.addWidget(self.btn_optimize_now)

        self.btn_live_telemetry = QPushButton(self.t("live_telemetry"))
        self.btn_live_telemetry.clicked.connect(self.show_live_telemetry)
        main_layout.addWidget(self.btn_live_telemetry)

        self.btn_delete_database = QPushButton("Delete Personal Data and Model")
        self.btn_delete_database.setObjectName("dangerButton")
        self.btn_delete_database.clicked.connect(self.delete_database)
        main_layout.addWidget(self.btn_delete_database)

        # Windows autostart button.
        self.btn_autostart = QPushButton("Start with Windows: " + ("ON" if is_autostart_enabled() else "OFF"))
        if is_autostart_enabled(): self.btn_autostart.setObjectName("autostartActive")
        self.btn_autostart.clicked.connect(self.toggle_autostart)
        main_layout.addWidget(self.btn_autostart)

        self.btn_settings = QPushButton("Settings: Balanced")
        self.settings_menu = QMenu(self)
        mode_group = QActionGroup(self)
        mode_group.setExclusive(True)
        for mode, config in OPTIMIZATION_MODES.items():
            if mode in self.custom_profiles:
                continue
            action = QAction(config["label"], self)
            action.setCheckable(True)
            action.setChecked(mode == self.optimization_mode)
            action.triggered.connect(lambda checked, selected_mode=mode: self.set_optimization_mode(selected_mode))
            mode_group.addAction(action)
            self.settings_menu.addAction(action)
        self.profile_menu = self.settings_menu.addMenu(self.t("custom_profiles"))
        self.profile_actions = {}
        for profile_id, profile in self.custom_profiles.items():
            self.add_profile_action(profile_id, profile)
        self.profile_menu.addSeparator()
        self.delete_profile_action = QAction(self.t("delete_profile"), self)
        self.delete_profile_action.triggered.connect(self.delete_custom_profile)
        self.profile_menu.addAction(self.delete_profile_action)
        self.language_menu = self.settings_menu.addMenu(
            f"{self.t('language')}: {self.t('english')}"
        )
        language_group = QActionGroup(self)
        language_group.setExclusive(True)
        self.language_actions = {}
        for language, label_key in (("en", "english"), ("tr", "turkish")):
            action = QAction(self.t(label_key), self)
            action.setCheckable(True)
            action.setChecked(language == self.language)
            action.triggered.connect(lambda checked, selected_language=language: self.set_language(selected_language))
            language_group.addAction(action)
            self.language_actions[language] = action
            self.language_menu.addAction(action)
        self.settings_menu.addSeparator()
        self.custom_profile_action = QAction(self.t("custom_profile"), self)
        self.custom_profile_action.triggered.connect(self.create_custom_profile)
        self.settings_menu.addAction(self.custom_profile_action)
        self.btn_settings.setMenu(self.settings_menu)
        main_layout.addWidget(self.btn_settings)

        self.create_tray_icon()

    def toggle_autostart(self):
        currently_enabled = is_autostart_enabled()
        if set_autostart(not currently_enabled):
            new_state = is_autostart_enabled()
            state_label = self.t("on") if new_state else self.t("off")
            self.btn_autostart.setText(f"{self.t('autostart')}: {state_label}")
            if new_state: self.btn_autostart.setObjectName("autostartActive")
            else: self.btn_autostart.setObjectName("")
            self.btn_autostart.setStyle(self.btn_autostart.style())

    def show_live_telemetry(self):
        if self.telemetry_dialog is not None:
            self.telemetry_dialog.show()
            self.telemetry_dialog.raise_()
            self.telemetry_dialog.activateWindow()
            return

        self.telemetry_dialog = QDialog(self)
        self.telemetry_dialog.setWindowTitle(self.t("live_telemetry_title"))
        self.telemetry_dialog.setMinimumSize(620, 420)
        layout = QVBoxLayout(self.telemetry_dialog)
        self.telemetry_log_view = QTextEdit()
        self.telemetry_log_view.setReadOnly(True)
        self.telemetry_log_view.setUndoRedoEnabled(False)
        self.telemetry_log_view.document().setMaximumBlockCount(1000)
        self.telemetry_log_view.setStyleSheet(
            "QTextEdit { background-color: #0d1117; color: #b9f6ca; "
            "border: 1px solid #344253; font-family: Consolas; font-size: 10pt; }"
        )
        layout.addWidget(self.telemetry_log_view)
        self.telemetry_status = QLabel()
        self.telemetry_status.setStyleSheet("color: #9aa7b8;")
        layout.addWidget(self.telemetry_status)
        clear_button = QPushButton("Clear" if self.language == "en" else "Temizle")
        clear_button.clicked.connect(self.telemetry_log_view.clear)
        layout.addWidget(clear_button)
        self.worker.telemetry_log.connect(self.append_telemetry_log)
        self.telemetry_dialog.finished.connect(self._close_telemetry_dialog)
        self.telemetry_timer = QTimer(self.telemetry_dialog)
        self.telemetry_timer.timeout.connect(self.append_telemetry_tick)
        self.telemetry_timer.start(1000)
        self.telemetry_dialog.show()
        self.append_telemetry_log(self.t("telemetry_ready"))
        self.append_telemetry_tick()

    def _close_telemetry_dialog(self):
        if self.telemetry_timer is not None:
            self.telemetry_timer.stop()
        try:
            self.worker.telemetry_log.disconnect(self.append_telemetry_log)
        except TypeError:
            pass
        self.telemetry_timer = None
        self.telemetry_log_view = None
        self.telemetry_dialog.deleteLater()
        self.telemetry_dialog = None

    def append_telemetry_log(self, message):
        if self.telemetry_log_view is None:
            return
        scrollbar = self.telemetry_log_view.verticalScrollBar()
        follow_bottom = scrollbar.value() >= scrollbar.maximum() - 2
        if "Bellek temizlendi" in message:
            color = "#ff4d6d"
        elif "Öncelik düşürüldü" in message:
            color = "#ffb347"
        elif "AI" in message or "optimizasyon" in message:
            color = "#f9e2af"
        else:
            color = "#b9f6ca"
        self.telemetry_log_view.setTextColor(QColor(color))
        self.telemetry_log_view.append(
            f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {message}"
        )
        if follow_bottom:
            scrollbar.setValue(scrollbar.maximum())

    def append_telemetry_tick(self):
        if self.telemetry_status is None:
            return
        data = getattr(self, "_latest_dashboard_data", {})
        self.telemetry_status.setText(
            self.t("telemetry_tick").format(
                events=data.get("telemetry_count", 0),
                ram=data.get("ram_percent", 0),
            )
        )

    def create_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QApplication.style().StandardPixmap.SP_ComputerIcon)
        self.tray_icon.setIcon(icon)

        tray_menu = QMenu()
        self.show_action = QAction(self.t("dashboard"), self)
        self.show_action.triggered.connect(self.showNormal)
        self.quit_action = QAction(self.t("exit"), self)
        self.quit_action.triggered.connect(self.close_app)

        tray_menu.addAction(self.show_action)
        tray_menu.addAction(self.quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def update_dashboard(self, data):
        self._latest_dashboard_data = data
        self.lbl_focus.setText(f"{self.t('foreground')}: {data['fg_name']}")
        self.lbl_window.setText(f"{self.t('window')}: {data.get('fg_title') or '-'}")
        self.lbl_pid.setText(f"{self.t('pid')}: {data.get('active_pid') or '-'}")
        policy = OPTIMIZATION_MODES[self.optimization_mode]["label"]
        self.lbl_mode.setText(f"{self.t('policy')}: {policy}")
        self.lbl_prediction.setText(
            f"{self.t('prediction')}: {data.get('predicted_next', self.t('not_enough_data'))}"
        )
        self.lbl_ram.setText(f"{self.t('ram_usage')}: {data['ram_percent']}% ({data['used_ram_mb']} MB)")
        self.lbl_ai_candidates.setText(f"{self.t('candidates')}: {data['candidates_count']} {self.t('processes')}")
        self.lbl_optimized.setText(
            f"{self.t('optimized')}: {data.get('optimized_count', 0)}"
        )
        self.lbl_released_memory.setText(
            f"{self.t('reduction')}: {data.get('released_memory_mb', 0.0):.2f} MB"
        )
        self.lbl_process_count.setText(f"{self.t('monitored')}: {data.get('process_count', 0)}")
        self.lbl_lowered_priority.setText(
            f"{self.t('lowered_priority')}: {data.get('lowered_priority_count', 0)}"
        )

        # Trigger automatic training every 15 minutes.
        if time.time() - self.last_train_time > self.retrain_interval_sec:
            self.last_train_time = time.time()
            self.trigger_retrain()
        elif (
            data.get("telemetry_count", 0) >= 100
            and self.worker.model is None
            and (self.retrain_worker is None or not self.retrain_worker.isRunning())
        ):
            self.last_train_time = time.time()
            self.trigger_retrain()

    def close_app(self):
        self.worker.stop()
        if self.retrain_worker is not None and self.retrain_worker.isRunning():
            self.retrain_worker.request_stop()
            self.retrain_worker.wait(10000)
        self.worker.wait(10000)
        QApplication.quit()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            self.t("title"),
            self.t("tray_message"),
            QSystemTrayIcon.MessageIcon.Information, 2000
        )

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RamOptimizerApp()
    window.show()
    sys.exit(app.exec())
