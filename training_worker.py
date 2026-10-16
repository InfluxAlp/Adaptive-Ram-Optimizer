import datetime
import gc
import os
import sqlite3

import joblib
import numpy as np
import pandas as pd
from PyQt6.QtCore import QThread, pyqtSignal
from sklearn.ensemble import RandomForestClassifier

from model_runtime import FEATURE_COLUMNS


class AutoTrainWorker(QThread):
    training_finished = pyqtSignal(str)

    def __init__(self, db_path="ml_dataset_telemetry.db", model_path="ram_optimizer_model.pkl",
                 cleanup_callback=None):
        super().__init__()
        self.db_path = db_path
        self.model_path = model_path
        self.cleanup_callback = cleanup_callback
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        try:
            conn = sqlite3.connect(self.db_path)
            df_snapshots = pd.read_sql_query(
                "SELECT * FROM system_snapshots ORDER BY snapshot_id DESC LIMIT 1000",
                conn,
            )
            df_telemetry = pd.read_sql_query(
                "SELECT * FROM process_telemetry ORDER BY id DESC LIMIT 15000",
                conn,
            )
            conn.close()

            if self._stop_requested:
                self.training_finished.emit("Training stopped")
                return

            if len(df_telemetry) < 100:
                self.training_finished.emit("Not enough data to train the model")
                return

            df = df_telemetry.copy()
            total_time = df["accumulated_fg_sec"] + df["accumulated_bg_sec"]
            df["focus_ratio"] = np.where(
                total_time > 0,
                df["accumulated_fg_sec"] / total_time,
                0.0,
            )
            df = df.merge(
                df_snapshots[["snapshot_id", "hour", "is_weekend", "ram_percent"]],
                on="snapshot_id",
                how="left",
            )
            df["target_optimize_candidate"] = np.where(
                (df["is_foreground"] == 0)
                & (df["focus_ratio"] < 0.10)
                & (df["working_set_mb"] > 30.0),
                1,
                0,
            )

            X = df[FEATURE_COLUMNS].fillna(0)
            y = df["target_optimize_candidate"]

            if self._stop_requested:
                self.training_finished.emit("Training stopped")
                return

            model = RandomForestClassifier(
                n_estimators=60,
                max_depth=10,
                random_state=42,
                n_jobs=1,
            )
            model.fit(X, y)

            if self._stop_requested:
                self.training_finished.emit("Training stopped")
                return

            joblib.dump(model, self.model_path)
            now_str = datetime.datetime.now().strftime("%H:%M:%S")
            self.training_finished.emit(f"Model updated ({now_str})")
        except Exception as error:
            self.training_finished.emit(f"Training error: {error}")
        finally:
            gc.collect()
            if self.cleanup_callback is not None:
                self.cleanup_callback(os.getpid())
