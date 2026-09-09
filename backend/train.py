import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.metrics import accuracy_score
import joblib

def clean_symptoms(sys_str):
    if pd.isna(sys_str):
        return ""
    # Split by comma and join by space
    return " ".join([s.strip().lower().replace(" ", "") for s in str(sys_str).split(',') if s.strip()])

def main():
    print("Loading data...")
    df = pd.read_csv('Healthcare.csv')
    df.dropna(subset=['Age', 'Gender', 'Symptoms', 'Disease'], inplace=True)
    
    # Preprocess symptoms
    df['Symptoms_Clean'] = df['Symptoms'].apply(clean_symptoms)
    
    X = df[['Age', 'Gender', 'Symptoms_Clean']]
    y = df['Disease']
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', 'passthrough', ['Age']),
            ('cat', OneHotEncoder(handle_unknown='ignore'), ['Gender']),
            ('text', CountVectorizer(), 'Symptoms_Clean')
        ]
    )
    
    pipeline = Pipeline([
        ('preprocessor', preprocessor),
        ('classifier', RandomForestClassifier(n_estimators=100, random_state=42))
    ])
    
    print("Splitting data...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    print("Training Random Forest Classifier model...")
    pipeline.fit(X_train, y_train)
    
    print("Testing model...")
    preds = pipeline.predict(X_test)
    acc = accuracy_score(y_test, preds)
    print(f"Model Accuracy on Test Set: {acc * 100:.2f}%")
    
    print("Saving model to disease_model.pkl...")
    joblib.dump(pipeline, 'disease_model.pkl')
    
    print("\n" + "="*50)
    print("PREVIEW:")
    
    # Random Sample Preview
    # Let's test "chest pain", "shortness of breath", "nausea", "sweating"
    # which should be High Risk / Heart Disease according to rules, let's see what model predicts.
    # Note: the model predicts what is in the CSV data.
    
    sample_age = 55
    sample_gender = 'Male'
    sample_symptoms = 'chest pain, shortness of breath, nausea, sweating'
    
    sample_df = pd.DataFrame([{
        'Age': sample_age,
        'Gender': sample_gender,
        'Symptoms_Clean': clean_symptoms(sample_symptoms)
    }])
    
    pred_disease = pipeline.predict(sample_df)[0]
    proba = pipeline.predict_proba(sample_df)
    max_proba = np.max(proba)
    
    print(f"Input Features:")
    print(f"  Age: {sample_age}")
    print(f"  Gender: {sample_gender}")
    print(f"  Symptoms: {sample_symptoms}")
    print(f"Predicted Disease: {pred_disease}")
    print(f"Confidence Probability: {max_proba * 100:.2f}%")
    print("="*50 + "\n")

if __name__ == '__main__':
    main()
