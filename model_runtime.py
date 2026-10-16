import pandas as pd


FEATURE_COLUMNS = [
    "hour", "is_weekend", "working_set_mb", "commit_size_mb",
    "cpu_percent", "thread_count", "handle_count",
    "accumulated_fg_sec", "accumulated_bg_sec", "focus_ratio",
    "ram_percent",
]


def predict_candidates(model, rows):
    if model is None or not rows:
        return {}

    frame = pd.DataFrame(rows, columns=["pid", *FEATURE_COLUMNS])
    features = frame[FEATURE_COLUMNS]
    predictions = model.predict(features)
    confidences = [0.0] * len(frame)

    if hasattr(model, "predict_proba") and 1 in model.classes_:
        positive_index = list(model.classes_).index(1)
        positive_rows = [index for index, value in enumerate(predictions) if int(value) == 1]
        if positive_rows:
            probabilities = model.predict_proba(features.iloc[positive_rows])
            for row_index, probability in zip(positive_rows, probabilities):
                confidences[row_index] = float(probability[positive_index])

    return {
        int(pid): {
            "prediction": int(prediction),
            "confidence": confidence,
        }
        for pid, prediction, confidence in zip(
            frame["pid"], predictions, confidences
        )
    }
