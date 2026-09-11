import os
from flask import Flask, request, jsonify, render_template
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Configure MongoDB Connection
# The MONGO_URI must be provided in the environment (e.g. Render environment variables or .env file)
app.config["MONGO_URI"] = os.environ.get("MONGO_URI")

# Initialize PyMongo
mongo = PyMongo(app)

@app.route('/')
def index():
    """Render the main single-page application."""
    return render_template('index.html')

# --- REST API Endpoints ---

@app.route('/api/workouts', methods=['GET'])
def get_workouts():
    """
    Read: Fetch all logged workouts.
    Includes seed data if the database is empty for demonstration purposes.
    """
    workouts_collection = mongo.db.workouts
    workouts = list(workouts_collection.find())

    # Format the data for JSON serialization (convert ObjectId to string)
    formatted_workouts = []
    for workout in workouts:
        workout['_id'] = str(workout['_id'])
        formatted_workouts.append(workout)

    return jsonify(formatted_workouts), 200


@app.route('/api/workouts', methods=['POST'])
def create_workout():
    """Create: Log a new exercise."""
    data = request.json
    
    # Basic validation
    if not all(k in data for k in ("exercise_name", "sets", "reps", "weight_kg", "date")):
        return jsonify({"error": "Missing required fields"}), 400

    new_workout = {
        "exercise_name": data['exercise_name'],
        "sets": int(data['sets']),
        "reps": int(data['reps']),
        "weight_kg": float(data['weight_kg']),
        "date": data['date']
    }

    result = mongo.db.workouts.insert_one(new_workout)
    new_workout['_id'] = str(result.inserted_id)

    return jsonify(new_workout), 201


@app.route('/api/workouts/<id>', methods=['PUT'])
def update_workout(id):
    """Update: Edit a specific workout entry."""
    data = request.json
    
    try:
        object_id = ObjectId(id)
    except:
        return jsonify({"error": "Invalid workout ID format"}), 400

    update_data = {}
    if 'exercise_name' in data: update_data['exercise_name'] = data['exercise_name']
    if 'sets' in data: update_data['sets'] = int(data['sets'])
    if 'reps' in data: update_data['reps'] = int(data['reps'])
    if 'weight_kg' in data: update_data['weight_kg'] = float(data['weight_kg'])
    if 'date' in data: update_data['date'] = data['date']

    result = mongo.db.workouts.update_one(
        {'_id': object_id},
        {'$set': update_data}
    )

    if result.matched_count == 0:
        return jsonify({"error": "Workout not found"}), 404

    return jsonify({"message": "Workout updated successfully"}), 200


@app.route('/api/workouts/<id>', methods=['DELETE'])
def delete_workout(id):
    """Delete: Remove a logged workout."""
    try:
        object_id = ObjectId(id)
    except:
        return jsonify({"error": "Invalid workout ID format"}), 400

    result = mongo.db.workouts.delete_one({'_id': object_id})

    if result.deleted_count == 0:
        return jsonify({"error": "Workout not found"}), 404

    return jsonify({"message": "Workout deleted successfully"}), 200


if __name__ == '__main__':
    # Default host and port for local development
    # In production (Render), these are often managed by gunicorn
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
