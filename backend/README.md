# MediTriage AI Backend

This is the Flask backend for the MediTriage AI application.

## Instructions:
1. Initialize the environment:
   `pip install -r requirements.txt`
2. Place `Healthcare.csv` inside the `/backend` folder.
3. Train the model:
   Run: `python train_model.py` (trains and saves the model to `.pkl` files)
4. Start the API server:
   Run: `python app.py` (starts Flask server on http://localhost:5000)

## API
- **Endpoint**: `POST /predict`
- **Request Body**:
  ```json
  {
    "age": 64,
    "gender": "Other",
    "symptoms": "muscle pain, headache, tremors, weight loss, depression, fever"
  }
  ```
- Returns the predicted disease, calculated risk level, confidence score, matching symptoms, and clinical recommendations as a JSON object.
