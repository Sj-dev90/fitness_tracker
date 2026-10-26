import os
import json
import socket
import io
import base64
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from dotenv import load_dotenv
import bcrypt
import jwt
import pyotp
import qrcode
from werkzeug.security import check_password_hash
from google import genai
from google.genai import types
from predictor import predict_next_weight

# Load environment variables from .env file
load_dotenv()

# JWT Secret Key - shared across all backend instances
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    JWT_SECRET_KEY = os.environ.get("SECRET_KEY", "fixed_dev_secret_key_12345")

# --- Password Hashing Helpers (bcrypt with legacy fallback) ---

def hash_password(pw: str) -> str:
    """Generate a bcrypt hash (cost factor 12) as a string."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pw.encode('utf-8'), salt).decode('utf-8')

def verify_password(pw: str, stored_hash: str) -> bool:
    """Verify password against bcrypt ($2b$) or legacy Werkzeug hashes (scrypt:, pbkdf2:)."""
    if not pw or not stored_hash:
        return False
    if stored_hash.startswith('$2b$'):
        return bcrypt.checkpw(pw.encode('utf-8'), stored_hash.encode('utf-8'))
    elif stored_hash.startswith(('scrypt:', 'pbkdf2:')):
        return check_password_hash(stored_hash, pw)
    return False

# --- JWT & RBAC Helpers & Decorators ---

def create_access_token(user_id: str, username: str, role: str) -> str:
    """Issue a 1-hour JWT token with user_id, username, and role claims."""
    payload = {
        "user_id": str(user_id),
        "username": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")

def decode_token(token: str):
    """Safely decode and validate a JWT."""
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
    except Exception:
        return None

def get_token_from_request():
    """Extract JWT from Authorization header ('Bearer <token>') or HttpOnly cookie ('token')."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return request.cookies.get("token") or request.cookies.get("jwt_token")

def require_auth(f):
    """Require valid JWT token. Return 401 on missing or invalid token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_token_from_request()
        if not token:
            return jsonify({"error": "Missing or invalid token"}), 401
        payload = decode_token(token)
        if not payload or payload.get("purpose") == "mfa":
            return jsonify({"error": "Missing or invalid token"}), 401
        request.current_user = payload
        session['user_id'] = payload['user_id']
        return f(*args, **kwargs)
    return decorated

def require_role(*allowed_roles):
    """Require valid JWT token AND that user's role is in allowed_roles."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = get_token_from_request()
            if not token:
                return jsonify({"error": "Missing or invalid token"}), 401
            payload = decode_token(token)
            if not payload or payload.get("purpose") == "mfa":
                return jsonify({"error": "Missing or invalid token"}), 401
            request.current_user = payload
            session['user_id'] = payload['user_id']
            user_role = payload.get("role", "member")
            if user_role not in allowed_roles:
                return jsonify({"error": "Insufficient role"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

# --- Flask App Setup ---

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fixed_dev_secret_key_12345")
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True

# Configure MongoDB Connection
app.config["MONGO_URI"] = os.environ.get("MONGO_URI")
try:
    mongo = PyMongo(app)
    db = mongo.db
    db.command('ping')
    print("Connected to MongoDB successfully!")
except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")

# Initialize Gemini Client
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# --- Health Check Endpoint (No Auth) ---

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "hostname": socket.gethostname()
    }), 200

# --- Load Test Endpoint (No Auth, Real Atlas Read) ---

@app.route('/api/loadtest', methods=['GET'])
def loadtest():
    try:
        workouts = list(mongo.db.workouts.find().sort("date", -1).limit(20))
        results = []
        for w in workouts:
            w['_id'] = str(w['_id'])
            results.append(w)
        return jsonify({
            "status": "success",
            "hostname": socket.gethostname(),
            "count": len(results),
            "data": results
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- HTML Routes ---

@app.route('/')
def index():
    """Render the main single-page application. Check JWT cookie for auth."""
    token = request.cookies.get('token')
    if token:
        payload = decode_token(token)
        if payload and payload.get('purpose') != 'mfa':
            return render_template('index.html')
    # Fall back to session check for backward compat
    if 'user_id' in session:
        return render_template('index.html')
    return redirect(url_for('login_page'))

@app.route('/login')
@app.route('/register')
def login_page():
    return render_template('login.html')

@app.route('/logout', methods=['GET'])
def logout_html():
    session.pop('user_id', None)
    response = redirect(url_for('login_page'))
    response.delete_cookie('token')
    return response

# --- Auth API Endpoints ---

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    if not data or not data.get('email') or not data.get('password') or not data.get('name'):
        return jsonify({"error": "Missing required fields"}), 400

    existing_user = mongo.db.users.find_one({"email": data['email']})
    if existing_user:
        return jsonify({"error": "User already exists"}), 400

    hashed_password = hash_password(data['password'])
    new_user = {
        "name": data['name'],
        "email": data['email'],
        "password": hashed_password,
        "goal": "Recomp",
        "split": "Push / Pull / Legs",
        "role": "member",
        "created_at": datetime.utcnow()
    }

    result = mongo.db.users.insert_one(new_user)
    user_id_str = str(result.inserted_id)

    # One-time migration: If this is the FIRST user, assign all orphaned records
    user_count = mongo.db.users.count_documents({})
    if user_count == 1:
        mongo.db.workouts.update_many({"user_id": {"$exists": False}}, {"$set": {"user_id": user_id_str}})
        mongo.db.meals.update_many({"user_id": {"$exists": False}}, {"$set": {"user_id": user_id_str}})

    token = create_access_token(user_id_str, new_user['name'], new_user['role'])
    session['user_id'] = user_id_str
    response = jsonify({
        "message": "Registered successfully",
        "name": new_user['name'],
        "goal": new_user['goal'],
        "split": new_user['split'],
        "role": new_user['role'],
        "token": token
    })
    response.set_cookie('token', token, httponly=True, samesite='Lax', max_age=3600)
    return response, 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"error": "Missing email or password"}), 400

    user = mongo.db.users.find_one({"email": data['email']})
    if not user or not verify_password(data['password'], user.get('password', '')):
        return jsonify({"error": "Invalid credentials"}), 401

    # Seamless migration: If legacy hash (not $2b$), rehash with bcrypt and update DB
    stored_hash = user.get('password', '')
    if not stored_hash.startswith('$2b$'):
        new_hash = hash_password(data['password'])
        mongo.db.users.update_one(
            {"_id": user['_id']},
            {"$set": {"password": new_hash}}
        )
        username = user.get('name') or user.get('email') or 'User'
        print(f"Upgraded password hash to bcrypt for user {username}", flush=True)

    user_id_str = str(user['_id'])
    role = user.get('role', 'member')

    # Check if TOTP is enabled — issue MFA token instead of full token
    if user.get('totp_enabled'):
        mfa_payload = {
            "user_id": user_id_str,
            "purpose": "mfa",
            "exp": datetime.utcnow() + timedelta(minutes=5)
        }
        mfa_token = jwt.encode(mfa_payload, JWT_SECRET_KEY, algorithm="HS256")
        return jsonify({"mfa_required": True, "mfa_token": mfa_token}), 200

    token = create_access_token(user_id_str, user.get('name', 'User'), role)
    session['user_id'] = user_id_str
    response = jsonify({
        "message": "Logged in successfully",
        "name": user.get('name', 'User'),
        "goal": user.get('goal', 'Recomp'),
        "split": user.get('split', 'Push / Pull / Legs'),
        "role": role,
        "token": token
    })
    response.set_cookie('token', token, httponly=True, samesite='Lax', max_age=3600)
    return response, 200

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    response = jsonify({"message": "Logged out"})
    response.delete_cookie('token')
    return response, 200

@app.route('/api/auth/me', methods=['GET'])
@require_auth
def auth_me():
    user_id = request.current_user['user_id']
    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "username": user.get('name', 'User'),
        "email": user.get('email', ''),
        "goal": user.get('goal', 'Recomp'),
        "split": user.get('split', 'Push / Pull / Legs'),
        "weight": user.get('weight', ''),
        "height": user.get('height', ''),
        "role": user.get('role', 'member'),
        "totp_enabled": user.get('totp_enabled', False)
    }), 200

# --- TOTP Endpoints ---

@app.route('/api/auth/totp/setup', methods=['POST'])
@require_auth
def totp_setup():
    """Generate a new TOTP secret and QR code for the user (pending confirmation)."""
    user_id = request.current_user['user_id']
    user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
    if not user:
        return jsonify({"error": "User not found"}), 404

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    email = user.get('email', user_id)
    uri = totp.provisioning_uri(name=email, issuer_name="FitnessTracker")

    # Store pending secret (not yet active)
    mongo.db.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'totp_pending_secret': secret}})

    # Generate QR code as base64 PNG
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    # Never log the secret
    return jsonify({"uri": uri, "qr_code": qr_b64}), 200

@app.route('/api/auth/totp/enable', methods=['POST'])
@require_auth
def totp_enable():
    """Confirm TOTP setup by verifying a code against the pending secret."""
    user_id = request.current_user['user_id']
    data = request.json
    code = data.get('code', '')

    user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
    if not user:
        return jsonify({"error": "User not found"}), 404

    secret = user.get('totp_pending_secret')
    if not secret:
        return jsonify({"error": "No pending TOTP setup. Call /api/auth/totp/setup first."}), 400

    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        return jsonify({"error": "Invalid code"}), 401

    mongo.db.users.update_one({'_id': ObjectId(user_id)}, {
        '$set': {'totp_secret': secret, 'totp_enabled': True},
        '$unset': {'totp_pending_secret': ''}
    })
    return jsonify({"message": "Two-factor authentication enabled"}), 200

@app.route('/api/auth/totp/verify', methods=['POST'])
def totp_verify():
    """Verify a TOTP code after password login, issue a full access token on success."""
    data = request.json
    mfa_token = data.get('mfa_token', '')
    code = data.get('code', '')

    if not mfa_token or not code:
        return jsonify({"error": "mfa_token and code are required"}), 400

    # Decode MFA token
    payload = decode_token(mfa_token)
    if not payload or payload.get('purpose') != 'mfa':
        return jsonify({"error": "Invalid or expired MFA token"}), 401

    user_id = payload['user_id']

    # Check rate limit lockout (stored in MongoDB — works across all 3 backends)
    lockout = mongo.db.totp_lockouts.find_one({'user_id': user_id})
    if lockout and lockout.get('locked_until') and lockout['locked_until'] > datetime.utcnow():
        return jsonify({"error": "Too many failed attempts. Try again in 5 minutes."}), 429

    user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
    if not user or not user.get('totp_enabled'):
        return jsonify({"error": "TOTP not enabled for this user"}), 400

    totp = pyotp.TOTP(user['totp_secret'])
    if not totp.verify(code, valid_window=1):
        # Increment fail count
        mongo.db.totp_lockouts.update_one(
            {'user_id': user_id},
            {'$inc': {'fail_count': 1}, '$set': {'user_id': user_id}},
            upsert=True
        )
        lockout = mongo.db.totp_lockouts.find_one({'user_id': user_id})
        if lockout and lockout.get('fail_count', 0) >= 5:
            mongo.db.totp_lockouts.update_one(
                {'user_id': user_id},
                {'$set': {'locked_until': datetime.utcnow() + timedelta(minutes=5)}}
            )
        return jsonify({"error": "Invalid code"}), 401

    # Success — clear lockout, issue full access token
    mongo.db.totp_lockouts.delete_one({'user_id': user_id})
    role = user.get('role', 'member')
    username = user.get('name', 'User')
    token = create_access_token(user_id, username, role)
    session['user_id'] = user_id
    response = jsonify({
        "message": "Authenticated",
        "name": username,
        "role": role,
        "goal": user.get('goal', 'Recomp'),
        "split": user.get('split', 'Push / Pull / Legs'),
        "token": token
    })
    response.set_cookie('token', token, httponly=True, samesite='Lax', max_age=3600)
    return response, 200

# --- User Preferences ---

@app.route('/api/user/preferences', methods=['POST'])
@require_auth
def update_preferences():
    user_id = request.current_user['user_id']
    data = request.json
    update_data = {}
    if 'goal' in data: update_data['goal'] = data['goal']
    if 'split' in data: update_data['split'] = data['split']
    if 'weight' in data: update_data['weight'] = data['weight']
    if 'height' in data: update_data['height'] = data['height']

    if update_data:
        mongo.db.users.update_one({'_id': ObjectId(user_id)}, {'$set': update_data})

    return jsonify({"message": "Preferences updated"}), 200

@app.route('/api/user/recommendation', methods=['POST'])
@require_auth
def ai_recommendation():
    if not gemini_client:
        return jsonify({"error": "Gemini API key is not configured."}), 500

    data = request.json
    weight = data.get('weight', '')
    height = data.get('height', '')
    goal = data.get('goal', '')
    split = data.get('split', '')

    prompt = f"User profile: Weight {weight}kg, Height {height}cm, Goal: {goal}, Split: {split}. Provide a tailored 3-sentence recommendation specifying target daily calorie surplus/deficit, protein targets (optimized for muscle preservation), and scheduling advice for their chosen split."

    system_instruction = "You are an expert AI fitness and nutrition coach. Always respond concisely in exactly 3 sentences with actionable numbers for calories, protein, and scheduling."

    try:
        response = gemini_client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_instruction)
        )
        return jsonify({"recommendation": response.text}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Meals ---

@app.route('/api/meals/today', methods=['GET'])
@require_auth
def get_meals_today():
    user_id = request.current_user['user_id']
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    meals = list(mongo.db.meals.find({
        "user_id": user_id,
        "date": today_str
    }))

    totals = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    for m in meals:
        totals["calories"] += float(m.get("calories", 0) or 0)
        totals["protein"] += float(m.get("protein_g", 0) or 0)
        totals["carbs"] += float(m.get("carbs_g", 0) or 0)
        totals["fat"] += float(m.get("fat_g", 0) or 0)

    return jsonify(totals), 200

@app.route('/api/splits/suggest', methods=['POST'])
def suggest_split():
    if not gemini_client:
        return jsonify({"error": "Gemini API key is not configured."}), 500

    data = request.json
    goal = data.get('goal', 'Recomp')
    split = data.get('split', 'Push / Pull / Legs')

    system_instruction = (
        "You are an expert fitness coach AI. The user is asking for a recommendation on how to adjust "
        "their volume, rep ranges, and calories based on their goal and training split. "
        "Provide a concise, 2-sentence actionable recommendation on rep ranges and calorie guidance."
    )
    prompt = f"Goal: {goal}. Split: {split}. Please provide a 2-sentence recommendation."

    try:
        response = gemini_client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_instruction)
        )
        return jsonify({"suggestion": response.text}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- Workout Endpoints (with RBAC) ---

@app.route('/api/workouts', methods=['GET'])
@require_auth
def get_workouts():
    """Read: Any authenticated role can fetch workouts. Unowned workouts belong to admin."""
    user_id = request.current_user['user_id']
    role = request.current_user.get('role', 'member')

    workouts_collection = mongo.db.workouts
    if role == 'admin':
        query = {"$or": [{"user_id": user_id}, {"user_id": {"$exists": False}}, {"user_id": None}]}
    else:
        query = {"user_id": user_id}

    workouts = list(workouts_collection.find(query).sort("date", -1))

    formatted_workouts = []
    for workout in workouts:
        workout['_id'] = str(workout['_id'])
        if 'user_id' in workout: del workout['user_id']
        formatted_workouts.append(workout)

    # Top 3 exercises from the last 7 days
    seven_days_ago = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d')
    pipeline = [
        {"$match": {"date": {"$gte": seven_days_ago}, **query}},
        {"$group": {"_id": "$exercise_name", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 3}
    ]
    top_exercises_cursor = workouts_collection.aggregate(pipeline)
    top_exercises = [doc["_id"] for doc in top_exercises_cursor]

    return jsonify({"workouts": formatted_workouts, "top_exercises": top_exercises}), 200


@app.route('/api/workouts', methods=['POST'])
@require_role('admin', 'member')
def create_workout():
    """Create: admin and member roles can log workouts. Viewers cannot."""
    user_id = request.current_user['user_id']
    data = request.json

    if not all(k in data for k in ("exercise_name", "sets", "reps", "weight_kg", "date")):
        return jsonify({"error": "Missing required fields"}), 400

    if len(data['exercise_name'].strip()) <= 1:
        return jsonify({"error": "Exercise name must be longer than 1 character"}), 400

    try:
        sets = int(data.get('sets') or 0)
        reps = int(data.get('reps') or 0)
        weight = float(data.get('weight_kg') or 0.0)
    except ValueError:
        return jsonify({"error": "Invalid numbers provided"}), 400

    if sets == 0 and reps == 0 and weight == 0:
        return jsonify({"error": "Sets, reps, and weight cannot all be zero"}), 400

    new_workout = {
        "exercise_name": data['exercise_name'].strip(),
        "sets": sets,
        "reps": reps,
        "weight_kg": weight,
        "date": data['date'],
        "user_id": user_id
    }

    result = mongo.db.workouts.insert_one(new_workout)
    new_workout['_id'] = str(result.inserted_id)
    del new_workout['user_id']

    return jsonify(new_workout), 201


@app.route('/api/workouts/ai-parse', methods=['POST'])
@require_role('admin', 'member')
def parse_workout_ai():
    """Create: Parse and log exercises via Gemini AI."""
    user_id = request.current_user['user_id']

    if not gemini_client:
        return jsonify({"error": "Gemini API key is not configured on the server."}), 500

    data = request.json
    text = data.get("text", "")

    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        today_str = datetime.utcnow().strftime('%Y-%m-%d')
        system_instruction = (
            "You are a workout parser. The user will provide a natural language workout summary. "
            "Parse it into a JSON array of objects. "
            "Each object must have exactly these keys: 'exercise_name' (string), 'sets' (integer), 'reps' (integer), 'weight_kg' (float, in kg), 'date' (string, 'YYYY-MM-DD'). "
            f"If date is not specified, use today's date: {today_str}. "
            "Do not output markdown formatting, just output the raw JSON array."
        )

        response = gemini_client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
            )
        )

        parsed_workouts = json.loads(response.text)

        if not isinstance(parsed_workouts, list) or len(parsed_workouts) == 0:
            return jsonify({"error": "Could not parse workouts."}), 400

        valid_workouts = []
        for w in parsed_workouts:
            name = str(w.get('exercise_name', '')).strip()
            if len(name) <= 1: continue

            s = int(w.get('sets', 1))
            r = int(w.get('reps', 1))
            wt = float(w.get('weight_kg', 0.0))
            if s == 0 and r == 0 and wt == 0: continue

            w['exercise_name'] = name
            w['sets'] = s
            w['reps'] = r
            w['weight_kg'] = wt
            if 'date' not in w or not w['date']:
                w['date'] = today_str
            w['user_id'] = user_id
            valid_workouts.append(w)

        if not valid_workouts:
            return jsonify({"error": "No valid workouts parsed."}), 400

        result = mongo.db.workouts.insert_many(valid_workouts)

        for i, _id in enumerate(result.inserted_ids):
            valid_workouts[i]['_id'] = str(_id)
            if 'user_id' in valid_workouts[i]: del valid_workouts[i]['user_id']

        return jsonify(valid_workouts), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/workouts/preview-parse', methods=['POST'])
def preview_parse_workout_ai():
    """Preview: Quick inexpensive parse of text without saving. Public (no auth needed)."""
    if not gemini_client:
        return jsonify({"error": "Gemini API key is not configured."}), 500

    data = request.json
    text = data.get("text", "")

    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        system_instruction = (
            "You are a fast workout parser. Parse the natural language workout summary into a JSON array of objects. "
            "Each object must have exactly these keys: 'exercise_name' (string), 'sets' (integer), 'reps' (integer), 'weight_kg' (float, in kg). "
            "Do not output markdown formatting, just output the raw JSON array."
        )

        response = gemini_client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=text,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
            )
        )

        parsed_workouts = json.loads(response.text)

        if not isinstance(parsed_workouts, list) or len(parsed_workouts) == 0:
            return jsonify([]), 200

        for w in parsed_workouts:
            w['sets'] = int(w.get('sets', 1))
            w['reps'] = int(w.get('reps', 1))
            w['weight_kg'] = float(w.get('weight_kg', 0.0))

        return jsonify(parsed_workouts), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/workouts/<id>', methods=['PUT'])
@require_auth
def update_workout(id):
    """Update: Edit a specific workout. Admin can edit any; member only their own; viewer cannot."""
    user = request.current_user
    role = user.get('role', 'member')

    if role == 'viewer':
        return jsonify({"error": "Insufficient role"}), 403

    try:
        object_id = ObjectId(id)
    except Exception:
        return jsonify({"error": "Invalid workout ID format"}), 400

    workout = mongo.db.workouts.find_one({'_id': object_id})
    if not workout:
        return jsonify({"error": "Workout not found"}), 404

    if role == 'member' and workout.get('user_id') != user['user_id']:
        return jsonify({"error": "Insufficient role"}), 403

    data = request.json
    update_data = {}
    if 'exercise_name' in data: update_data['exercise_name'] = data['exercise_name']
    if 'sets' in data: update_data['sets'] = int(data['sets'])
    if 'reps' in data: update_data['reps'] = int(data['reps'])
    if 'weight_kg' in data: update_data['weight_kg'] = float(data['weight_kg'])
    if 'date' in data: update_data['date'] = data['date']

    mongo.db.workouts.update_one({'_id': object_id}, {'$set': update_data})
    return jsonify({"message": "Workout updated successfully"}), 200


@app.route('/api/workouts/<id>', methods=['DELETE'])
@require_auth
def delete_workout(id):
    """Delete: Admin can delete any workout; member only their own; viewer cannot."""
    user = request.current_user
    role = user.get('role', 'member')

    if role == 'viewer':
        return jsonify({"error": "Insufficient role"}), 403

    try:
        object_id = ObjectId(id)
    except Exception:
        return jsonify({"error": "Invalid workout ID format"}), 400

    workout = mongo.db.workouts.find_one({'_id': object_id})
    if not workout:
        return jsonify({"error": "Workout not found"}), 404

    if role == 'member' and workout.get('user_id') != user['user_id']:
        return jsonify({"error": "Insufficient role"}), 403

    mongo.db.workouts.delete_one({'_id': object_id})
    return jsonify({"message": "Workout deleted successfully"}), 200


@app.route('/api/predict/<exercise_name>', methods=['GET'])
@require_auth
def get_prediction(exercise_name):
    """Predict: Get recommended target weight for an exercise."""
    user_id = request.current_user['user_id']
    workouts_collection = mongo.db.workouts
    query = {"user_id": user_id}
    query["exercise_name"] = {"$regex": f"^{exercise_name}$", "$options": "i"}

    workouts = list(workouts_collection.find(query).sort("date", 1))

    suggested, plateau, conf = predict_next_weight(workouts)

    return jsonify({
        "exercise_name": exercise_name,
        "suggested_weight": suggested,
        "plateau_risk": plateau,
        "confidence": conf,
        "history_count": len(workouts)
    }), 200

# --- Meal Analysis ---

@app.route('/api/meals/analyze', methods=['POST'])
def analyze_meal():
    """Analyze and log a meal via Gemini AI."""
    if not gemini_client:
        return jsonify({"error": "Gemini API key is not configured."}), 500

    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "Empty file"}), 400

    try:
        image_bytes = file.read()

        system_instruction = (
            "You are an expert nutritional analysis AI. Analyze the food in this image. "
            "Pay special attention to identifying high-protein vegetarian and egg-based "
            "ingredients to ensure accurate macro estimates for muscle preservation goals. "
            "Return a strict JSON object with these keys: "
            "food_name (string), confidence_match (string like '92% match'), "
            "calories (int), protein_g (int), and carbs_g (int)."
        )

        response = gemini_client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=file.mimetype),
                "Analyze this meal."
            ],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
            )
        )

        meal_data = json.loads(response.text)
        return jsonify(meal_data), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/meals/confirm', methods=['POST'])
@require_auth
def confirm_meal():
    """Confirm and save a meal."""
    user_id = request.current_user['user_id']
    data = request.json
    if not data or 'food_name' not in data:
        return jsonify({"error": "Missing meal data"}), 400

    meal_data = {
        "food_name": data.get("food_name"),
        "confidence_match": data.get("confidence_match", ""),
        "calories": int(data.get("calories") or 0),
        "protein_g": int(data.get("protein_g") or 0),
        "carbs_g": int(data.get("carbs_g") or 0),
        "user_id": user_id,
        "date": datetime.utcnow().strftime('%Y-%m-%d')
    }

    result = mongo.db.meals.insert_one(meal_data)
    meal_data['_id'] = str(result.inserted_id)
    del meal_data['user_id']

    return jsonify(meal_data), 201

# --- Analytics ---

@app.route('/api/analytics', methods=['GET'])
@require_auth
def get_analytics():
    """Read: Fetch aggregated analytics data for Chart.js."""
    user_id = request.current_user['user_id']
    match_query = {"user_id": user_id}

    # 1. Volume Distribution: Total sets per exercise
    volume_pipeline = [
        {"$match": match_query},
        {"$group": {"_id": "$exercise_name", "total_sets": {"$sum": "$sets"}}},
        {"$sort": {"total_sets": -1}}
    ]
    volume_data = list(mongo.db.workouts.aggregate(volume_pipeline))

    vol_labels = [item["_id"] for item in volume_data]
    vol_values = [item["total_sets"] for item in volume_data]

    # 2. Strength Progression: Max 1RM per date per exercise
    strength_pipeline = [
        {"$match": match_query},
        {"$addFields": {
            "one_rm": {"$multiply": ["$weight_kg", {"$add": [1, {"$divide": ["$reps", 30]}]}]}
        }},
        {"$group": {
            "_id": {"date": "$date", "exercise": "$exercise_name"},
            "max_1rm": {"$max": "$one_rm"}
        }},
        {"$sort": {"_id.date": 1}}
    ]
    strength_data = list(mongo.db.workouts.aggregate(strength_pipeline))

    dates = sorted(list(set([item["_id"]["date"] for item in strength_data])))
    exercises = list(set([item["_id"]["exercise"] for item in strength_data]))

    datasets = []
    for ex in exercises:
        data_points = []
        for d in dates:
            record = next((item for item in strength_data if item["_id"]["date"] == d and item["_id"]["exercise"] == ex), None)
            data_points.append(round(record["max_1rm"], 2) if record else None)
        datasets.append({
            "label": ex,
            "data": data_points,
            "spanGaps": True
        })

    return jsonify({
        "volume": {
            "labels": vol_labels,
            "data": vol_values
        },
        "strength": {
            "labels": dates,
            "datasets": datasets
        }
    }), 200

# --- AI Coach Review ---

@app.route('/api/ai/coach-review', methods=['GET'])
@require_auth
def ai_coach_review():
    try:
        user_id = request.current_user['user_id']
        if not gemini_client:
            return jsonify({"error": "Gemini API key is not configured."}), 500

        thirty_days_ago_dt = datetime.utcnow() - timedelta(days=30)
        thirty_days_ago_str = thirty_days_ago_dt.strftime('%Y-%m-%d')

        user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
        weight = user.get('weight', 'unknown') if user else 'unknown'
        goal = user.get('goal', 'Recomp') if user else 'Recomp'

        workouts = list(mongo.db.workouts.find({
            "user_id": user_id,
            "date": {"$gte": thirty_days_ago_dt.isoformat().split('T')[0]}
        }))
        workouts_alt = list(mongo.db.workouts.find({
            "user_id": user_id,
            "date": {"$gte": thirty_days_ago_str}
        }))
        if len(workouts_alt) > len(workouts): workouts = workouts_alt

        meals = list(mongo.db.meals.find({
            "user_id": user_id,
            "date": {"$gte": thirty_days_ago_str}
        }))

        total_sets = 0
        for w in workouts:
            try:
                val = w.get('sets', 0)
                total_sets += int(val) if val else 0
            except (ValueError, TypeError):
                pass

        total_meals = len(meals)

        total_cals = 0
        total_pro = 0
        for m in meals:
            try:
                c = m.get('calories', 0)
                p = m.get('protein_g', 0)
                total_cals += float(c) if c else 0
                total_pro += float(p) if p else 0
            except (ValueError, TypeError):
                pass

        avg_cals = total_cals / total_meals if total_meals > 0 else 0
        avg_pro = total_pro / total_meals if total_meals > 0 else 0

        workouts_str = f"{len(workouts)} workouts, {total_sets} total sets" if workouts else "No data logged yet"
        meals_str = f"{total_meals} meals logged, Avg Daily Cals: {avg_cals:.0f}, Avg Daily Pro: {avg_pro:.0f}g" if meals else "No data logged yet"

        prompt = f"""
        Act as an elite strength and nutrition coach. The user is focusing on weight loss while preserving muscle mass, and follows a vegetarian diet that includes eggs. Analyze their provided workout history and meal logs. Provide actionable, concise advice on plateau-breaking, progressive overload, and high-protein vegetarian/egg-based meal adjustments.
        
        User Profile: Weight {weight}kg, Goal {goal}.
        Last 30 Days Stats:
        - Workouts: {workouts_str}
        - Nutrition: {meals_str}
        """

        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return jsonify({"insights": response.text}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
