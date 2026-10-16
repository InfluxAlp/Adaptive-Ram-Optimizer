import sqlite3
import pandas as pd
import numpy as np
import joblib

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score

def load_dataset(db_path="ml_dataset_telemetry.db"):
    conn = sqlite3.connect(db_path)
    df_snapshots = pd.read_sql_query("SELECT * FROM system_snapshots", conn)
    df_telemetry = pd.read_sql_query("SELECT * FROM process_telemetry", conn)
    conn.close()

    df = df_telemetry.copy()
    
    # Feature Engineering (Öznitelik Türetme)
    total_time = df['accumulated_fg_sec'] + df['accumulated_bg_sec']
    df['focus_ratio'] = np.where(total_time > 0, df['accumulated_fg_sec'] / total_time, 0.0)
    
    # Snapshot verisini birleştir
    df = df.merge(df_snapshots[['snapshot_id', 'hour', 'is_weekend', 'ram_percent']], on='snapshot_id', how='left')

    # Hedef Değişken (Target Label y): 
    # Arka planda + Düşük Odak Oranı (<0.10) + Bellek Tüketimi >30 MB ise 1 (Aday), değilse 0
    df['target_optimize_candidate'] = np.where(
        (df['is_foreground'] == 0) & 
        (df['focus_ratio'] < 0.10) & 
        (df['working_set_mb'] > 30.0), 
        1, 0
    )

    feature_cols = ['hour', 'is_weekend', 'working_set_mb', 'commit_size_mb', 
                    'cpu_percent', 'thread_count', 'handle_count', 
                    'accumulated_fg_sec', 'accumulated_bg_sec', 'focus_ratio', 'ram_percent']
    
    X = df[feature_cols]
    y = df['target_optimize_candidate']
    
    return X, y, feature_cols

def train_model():
    print("Loading dataset from the database...")
    X, y, feature_names = load_dataset()

    # Veriyi Eğitim (%80) ve Test (%20) olarak böl
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    print(f"Training rows: {X_train.shape[0]} | Test rows: {X_test.shape[0]}")
    print("Training Random Forest model...\n")

    # Random Forest Sınıflandırıcı Modelinin Kurulumu
    model = RandomForestClassifier(
        n_estimators=100,      # 100 karar ağacı birleşimi
        max_depth=12,          # Ezberlemeyi (overfitting) önlemek için derinlik sınırı
        random_state=42,
        n_jobs=1               # Eğitim sırasında ani CPU sıçramalarını önle
    )

    # Modeli Eğit
    model.fit(X_train, y_train)

    # Test Verisi Üzerinde Tahmin Yap
    y_pred = model.predict(X_test)

    # --- MODEL PERFORMANS METRİKLERİ ---
    acc = accuracy_score(y_test, y_pred)
    print("=" * 60)
    print(f"MODEL ACCURACY: {round(acc * 100, 2)}%")
    print("=" * 60)
    
    print("\nClassification report:")
    print(classification_report(y_test, y_pred, target_names=['Protected (0)', 'Optimization candidate (1)']))

    # --- ÖZNİTELİK ÖNEM DERECELERİ (FEATURE IMPORTANCE) ---
    importances = model.feature_importances_
    feat_importance_df = pd.DataFrame({
        'Feature': feature_names,
        'Importance (%)': np.round(importances * 100, 2)
    }).sort_values(by='Importance (%)', ascending=False)

    print("\nFEATURE IMPORTANCE:")
    print("-" * 60)
    print(feat_importance_df.to_string(index=False))

    # --- MODELİ DİSKE KAYDETME ---
    model_filename = "ram_optimizer_model.pkl"
    joblib.dump(model, model_filename)
    print(f"\nTrained model saved: {model_filename}")

if __name__ == "__main__":
    train_model()