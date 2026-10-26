# Fitness & Workout Tracker

A full-stack web application designed for tracking strength training progress. This project fulfills the requirements of a cloud-ready web application using a Python Flask backend, MongoDB Atlas database, and a Vanilla JavaScript/HTML/CSS frontend.

## Directory Structure

```text
fitness_tracker/
├── app.py                 # Flask application backend and REST API endpoints
├── requirements.txt       # Python dependencies for the environment and Render deployment
├── .env.example           # Example environment variables template for local development
├── README.md              # Project documentation, deployment guide, and API reference
├── static/
│   ├── style.css          # CSS styles (Dark mode with neon green accents)
│   └── script.js          # Vanilla JavaScript handling DOM updates and API calls (fetch)
└── templates/
    └── index.html         # Main HTML view
```

## Local Setup Instructions

1. **Install Python**: Ensure you have Python 3 installed.
2. **Setup Virtual Environment** (optional but recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```
3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
4. **Configure Database**:
   - Create a free tier cluster on [MongoDB Atlas](https://www.mongodb.com/cloud/atlas).
   - Obtain your connection string.
   - Copy `.env.example` to `.env` and paste your connection string.
5. **Run the App**:
   ```bash
   python app.py
   ```
   Open your browser to `http://localhost:5000`.

---

## Deployment Configuration (Render)

This repository is configured to be easily deployed as a **Web Service** on Render.

1. Create a new Web Service on Render and connect this repository.
2. Ensure the following configurations are set in the Render dashboard:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app` (This uses the gunicorn WSGI server included in `requirements.txt`)
3. **Environment Variables**:
   - Add a new environment variable in the Render dashboard.
   - **Key**: `MONGO_URI`
   - **Value**: `<Your complete MongoDB Atlas connection string>`
4. Click **Deploy**. Render will install dependencies and start the app using `gunicorn`.

---

## API Documentation Template

### Base URL
`/api/workouts`

### 1. Get All Workouts (Read)
- **Endpoint**: `GET /api/workouts`
- **Description**: Retrieves a list of all logged workouts. If the database is empty, it will automatically populate with seed data (e.g., Incline Bench Press, Tricep Pushdowns) and return it.
- **Success Response**: `200 OK`
- **Response Body**: Array of JSON objects.
  ```json
  [
    {
      "_id": "653a1b2c3d...",
      "exercise_name": "Incline Bench Press",
      "sets": 4,
      "reps": 8,
      "weight_kg": 70,
      "date": "2023-10-25"
    }
  ]
  ```

### 2. Log New Workout (Create)
- **Endpoint**: `POST /api/workouts`
- **Description**: Creates a new workout entry.
- **Request Body**: JSON object.
  ```json
  {
    "exercise_name": "Deadlift",
    "sets": 3,
    "reps": 5,
    "weight_kg": 100,
    "date": "2023-10-26"
  }
  ```
- **Success Response**: `201 Created`
- **Response Body**: Returns the created JSON object including the generated `_id`.

### 3. Edit Workout (Update)
- **Endpoint**: `PUT /api/workouts/<id>`
- **Description**: Updates an existing workout entry by its MongoDB ObjectId.
- **Request Body**: JSON object containing fields to update.
- **Success Response**: `200 OK`
- **Response Body**: `{"message": "Workout updated successfully"}`

### 4. Delete Workout (Delete)
- **Endpoint**: `DELETE /api/workouts/<id>`
- **Description**: Deletes a specific workout entry by its ID.
- **Success Response**: `200 OK`
- **Response Body**: `{"message": "Workout deleted successfully"}`
