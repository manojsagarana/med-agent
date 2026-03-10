import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report,
)

# 1) Load dataset
df = pd.read_csv("data/Medical_Equipment_Health_Dataset.csv")
print("Rows in raw CSV:", len(df))

# 2) Create a binary label from Error_Code
# In your data: '000' is the normal (no error) code.
NORMAL_CODES = {"000"}  # extend if you add other normal codes later

df["Failure"] = df["Error_Code"].fillna("").astype(str).str.strip()
df["Failure"] = (~df["Failure"].isin(NORMAL_CODES)).astype(int)

print("\nFailure label distribution (0=normal, 1=failure):")
print(df["Failure"].value_counts())

# 3) Choose features that should exist for all machines
feature_cols = [
    "Component_Temp",
    "Gradient_Coil_Temp",
    "Vibration_Level",
    "Cooling_System_Performance",
]

label_col = "Failure"

# Keep only rows where these columns are present
before = len(df)
df = df.dropna(subset=feature_cols + [label_col])
after = len(df)

print(f"\nRows before dropna: {before}")
print(f"Rows after dropna : {after}")

if after == 0:
    raise SystemExit("No rows left after dropna; need to adjust feature_cols.")

X = df[feature_cols]
y = df[label_col].astype(int)

# Check that we have both classes
print("\nLabel distribution after cleaning:")
print(y.value_counts())

if y.nunique() < 2:
    raise SystemExit("Only one class present after cleaning; cannot compute meaningful accuracy.")

# 4) Train/test split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# 5) Train model
model = RandomForestClassifier(
    n_estimators=200,
    max_depth=None,
    random_state=42,
    n_jobs=-1,
)
model.fit(X_train, y_train)

# 6) Evaluate
y_pred = model.predict(X_test)

acc = accuracy_score(y_test, y_pred)
prec = precision_score(y_test, y_pred, zero_division=0)
rec = recall_score(y_test, y_pred, zero_division=0)
f1 = f1_score(y_test, y_pred, zero_division=0)
cm = confusion_matrix(y_test, y_pred)

print("\n=== Glitchcon Error_Code (Failure) Prediction Metrics ===")
print(f"Accuracy      : {acc:.3f}")
print(f"Precision     : {prec:.3f}")
print(f"Recall        : {rec:.3f}")
print(f"F1-score      : {f1:.3f}")
print("Confusion matrix [ [TN FP] [FN TP] ]:")
print(cm)
print("\nDetailed report:")
print(classification_report(y_test, y_pred, digits=3))