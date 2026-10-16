import os
import sys
import time
import sqlite3
import datetime
import ctypes
from ctypes import wintypes
import psutil

# Windows Win32 API eriÅŸimleri
user32 = ctypes.windll.user32

def get_foreground_info():
    """EkranÄ±n en Ã¶nÃ¼ndeki (odaktaki) pencerenin PID, sÃ¼reÃ§ adÄ± ve pencere baÅŸlÄ±ÄŸÄ±nÄ± Ã§eker."""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None, "Desktop/None", ""
        
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        
        # Pencere baÅŸlÄ±ÄŸÄ±nÄ± alma
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        window_title = buff.value
        
        proc = psutil.Process(pid.value)
        return pid.value, proc.name(), window_title
    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
        return None, "Unknown", ""

def init_advanced_db(db_path="ml_dataset_telemetry.db"):
    """
    Yapay ZekÃ¢ eÄŸitimi iÃ§in optimize edilmiÅŸ, WAL modunda Ã§alÄ±ÅŸan 
    iliÅŸkili veritabanÄ± ÅŸemasÄ±nÄ± oluÅŸturur.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # YÃ¼ksek hÄ±zlÄ± okuma/yazma ve kilitlenmeyi Ã¶nlemek iÃ§in WAL modu
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")

    # 1. TABLO: Genel Sistem YÃ¼kÃ¼ ve Zaman BaÄŸlamÄ± (System Snapshots)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_snapshots (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            hour INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,
            is_weekend INTEGER NOT NULL,
            total_cpu_percent REAL NOT NULL,
            used_ram_mb REAL NOT NULL,
            free_ram_mb REAL NOT NULL,
            ram_percent REAL NOT NULL,
            active_pid INTEGER,
            active_process_name TEXT,
            active_window_title TEXT
        )
    """)

    # 2. TABLO: DetaylÄ± SÃ¼reÃ§ Metrikleri ve DavranÄ±ÅŸ Ã–zellikleri (Process Metrics)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS process_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER,
            pid INTEGER NOT NULL,
            process_name TEXT NOT NULL,
            is_foreground INTEGER NOT NULL,
            working_set_mb REAL NOT NULL,
            commit_size_mb REAL NOT NULL,
            cpu_percent REAL,
            thread_count INTEGER,
            handle_count INTEGER,
            read_bytes_sec REAL,
            write_bytes_sec REAL,
            accumulated_fg_sec REAL DEFAULT 0,
            accumulated_bg_sec REAL DEFAULT 0,
            FOREIGN KEY(snapshot_id) REFERENCES system_snapshots(snapshot_id)
        )
    """)

    # HÄ±zlÄ± Yapay ZekÃ¢ sorgularÄ± iÃ§in Ä°ndeksler (Indexing)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_snap_time ON system_snapshots(timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_proc_name ON process_telemetry(process_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_snap_id ON process_telemetry(snapshot_id);")

    conn.commit()
    return conn

def main():
    """Collect foreground events without periodic polling."""
    from optimizer_core import OptimizerCore
    from queue import Queue

    db_path = "ml_dataset_telemetry.db"
    connection = init_advanced_db(db_path)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS event_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            pid INTEGER NOT NULL,
            process_name TEXT NOT NULL,
            window_title TEXT,
            previous_focus_duration_ms INTEGER NOT NULL
        )
    """)
    connection.commit()
    events = Queue()
    core = OptimizerCore()
    core.start(events.put)
    print("[System Active] Event-driven telemetry collector started.")
    print(f"[Database] {os.path.abspath(db_path)}")
    try:
        while (event := events.get()) is not None:
            connection.execute(
                "INSERT INTO event_telemetry "
                "(timestamp,pid,process_name,window_title,previous_focus_duration_ms) "
                "VALUES (?,?,?,?,?)",
                (event.timestamp, event.process_id, event.process_name,
                 event.window_title, event.previous_focus_duration_ms),
            )
            connection.commit()
            print(
                f"[{event.timestamp}] Foreground: {event.process_name} "
                f"(PID {event.process_id}), previous focus: "
                f"{event.previous_focus_duration_ms} ms"
            )
    except KeyboardInterrupt:
        pass
    finally:
        core.stop()
        connection.close()


if __name__ == "__main__":
    main()