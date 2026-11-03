"""
Train a Symptom -> Disease text classifier and save it as a pickle file.

Usage:
    python train_symptom2disease.py
    python train_symptom2disease.py --data Symptom2Disease_combined.csv --out symptom2disease_model.pkl

Requires: pandas, scikit-learn
"""
import argparse
import pickle

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV


def build_pipeline(clf):
    # Word n-grams + character n-grams works best on this small dataset
    features = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True)),
    ])
    return Pipeline([("features", features), ("clf", clf)])


def top_k_accuracy(model, X, y, k=3):
    proba = model.predict_proba(X)
    top = model.classes_[proba.argsort(axis=1)[:, -k:]]
    return sum(t in row for t, row in zip(y, top)) / len(y)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="Symptom2Disease_combined.csv")
    ap.add_argument("--out", default="symptom2disease_model.pkl")
    args = ap.parse_args()

    # ---- 1. Load & clean -------------------------------------------------
    df = pd.read_csv(args.data)
    df = df.drop(columns=[c for c in df.columns if c.startswith("Unnamed")], errors="ignore")
    df = df.dropna(subset=["text", "label"]).drop_duplicates()
    df["text"] = df["text"].str.strip()
    df["label"] = df["label"].str.strip()
    print(f"Rows: {len(df)} | Classes: {df['label'].nunique()}")

    X, y = df["text"], df["label"]

    # ---- 2. Compare candidate models with 5-fold CV ----------------------
    candidates = {
        "LogisticRegression": LogisticRegression(max_iter=3000, C=50),
        "LinearSVC": LinearSVC(C=1.0),
    }
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = {}
    for name, clf in candidates.items():
        s = cross_val_score(build_pipeline(clf), X, y, cv=cv, scoring="accuracy")
        scores[name] = s.mean()
        print(f"{name:20s} CV accuracy: {s.mean():.3f} (+/- {s.std():.3f})")
    best = max(scores, key=scores.get)
    print(f"Best model: {best}")

    # ---- 3. Hold-out evaluation ------------------------------------------
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
    eval_model = build_pipeline(candidates[best]).fit(X_tr, y_tr)
    pred = eval_model.predict(X_te)
    print(f"\nHold-out accuracy: {accuracy_score(y_te, pred):.3f}")
    if hasattr(eval_model, "predict_proba"):
        print(f"Hold-out top-3 accuracy: {top_k_accuracy(eval_model, X_te, y_te, 3):.3f}")
    # print(classification_report(y_te, pred, zero_division=0))  # uncomment for per-class details

    # ---- 4. Final model on ALL data (with probabilities) -----------------
    # Calibrate so predict_proba works for LinearSVC; LogisticRegression has it natively.
    final_clf = (
        CalibratedClassifierCV(LinearSVC(C=1.0), cv=3)
        if best == "LinearSVC" else LogisticRegression(max_iter=3000, C=50)
    )
    final_model = build_pipeline(final_clf).fit(X, y)

    # ---- 5. Save pickle --------------------------------------------------
    with open(args.out, "wb") as f:
        pickle.dump(final_model, f)
    print(f"\nSaved model -> {args.out}")

    # ---- 6. Reload test --------------------------------------------------
    with open(args.out, "rb") as f:
        loaded = pickle.load(f)
    sample = "I have an itchy rash between my toes and the skin is peeling"
    probs = loaded.predict_proba([sample])[0]
    top3 = sorted(zip(loaded.classes_, probs), key=lambda t: -t[1])[:3]
    print("\nSample prediction:", sample)
    for label, p in top3:
        print(f"  {label:35s} {p:.3f}")


if __name__ == "__main__":
    main()
