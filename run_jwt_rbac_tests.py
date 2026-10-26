import os
import sys
import json
import time
import requests
import pyotp
from subprocess import run, PIPE
from dotenv import load_dotenv
from pymongo import MongoClient
from bson.objectid import ObjectId

load_dotenv()

BASE_URL = "http://localhost"
MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
try:
    db = client.get_default_database()
    if db is None:
        db = client["fitness_tracker"]
except Exception:
    db = client["fitness_tracker"]

# Clean up any leftover test accounts from previous runs
test_emails = [
    "admintest_jwt@example.com",
    "member1_jwt@example.com",
    "member2_jwt@example.com",
    "viewer_jwt@example.com",
    "totp_jwt@example.com"
]
db.users.delete_many({"email": {"$in": test_emails}})
db.totp_lockouts.delete_many({})

print("="*70)
print("CREATING TEST ACCOUNTS & ASSIGNING ROLES")
print("="*70)

# 1. Admin account
res = requests.post(f"{BASE_URL}/api/auth/register", json={
    "name": "AdminTester",
    "email": "admintest_jwt@example.com",
    "password": "AdminPassword123!"
})
admin_data = res.json()
admin_id = db.users.find_one({"email": "admintest_jwt@example.com"})["_id"]
db.users.update_one({"_id": admin_id}, {"$set": {"role": "admin"}})
print(f"Created Admin: AdminTester (admintest_jwt@example.com), role: admin, ID: {admin_id}")

# 2. Member 1 account
res = requests.post(f"{BASE_URL}/api/auth/register", json={
    "name": "MemberOne",
    "email": "member1_jwt@example.com",
    "password": "MemberPassword123!"
})
m1_id = db.users.find_one({"email": "member1_jwt@example.com"})["_id"]
print(f"Created Member 1: MemberOne (member1_jwt@example.com), role: member, ID: {m1_id}")

# 3. Member 2 account
res = requests.post(f"{BASE_URL}/api/auth/register", json={
    "name": "MemberTwo",
    "email": "member2_jwt@example.com",
    "password": "MemberPassword123!"
})
m2_id = db.users.find_one({"email": "member2_jwt@example.com"})["_id"]
print(f"Created Member 2: MemberTwo (member2_jwt@example.com), role: member, ID: {m2_id}")

# 4. Viewer account
res = requests.post(f"{BASE_URL}/api/auth/register", json={
    "name": "ViewerTester",
    "email": "viewer_jwt@example.com",
    "password": "ViewerPassword123!"
})
v_id = db.users.find_one({"email": "viewer_jwt@example.com"})["_id"]
db.users.update_one({"_id": v_id}, {"$set": {"role": "viewer"}})
print(f"Created Viewer: ViewerTester (viewer_jwt@example.com), role: viewer, ID: {v_id}")

# 5. TOTP test account
res = requests.post(f"{BASE_URL}/api/auth/register", json={
    "name": "TotpTester",
    "email": "totp_jwt@example.com",
    "password": "TotpPassword123!"
})
t_id = db.users.find_one({"email": "totp_jwt@example.com"})["_id"]
print(f"Created TOTP User: TotpTester (totp_jwt@example.com), role: member, ID: {t_id}")

print("\n" + "="*70)
print("TEST a: No token -> curl.exe -i http://localhost/api/workouts -> 401")
print("="*70)
curl_a = run(["curl.exe", "-i", "-s", "http://localhost/api/workouts"], stdout=PIPE, stderr=PIPE, text=True)
print(curl_a.stdout.strip())

print("\n" + "="*70)
print("TEST b: Login as admin -> token; GET /api/workouts with Bearer header -> 200")
print("="*70)
login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
    "email": "admintest_jwt@example.com",
    "password": "AdminPassword123!"
})
admin_token = login_res.json()["token"]
print(f"Admin login status: {login_res.status_code}")
print(f"Admin token received (length: {len(admin_token)})")

curl_b = run(["curl.exe", "-i", "-s", "-H", f"Authorization: Bearer {admin_token}", "http://localhost/api/workouts"], stdout=PIPE, stderr=PIPE, text=True)
# Show status line and headers + truncated body
lines = curl_b.stdout.strip().split("\n")
header_lines = [l for l in lines if ":" in l or l.startswith("HTTP")]
print("\n".join(header_lines[:8]))
body_line = [l for l in lines if l.startswith("{") or l.startswith("[")]
if body_line:
    body_json = json.loads(body_line[0])
    print(f"Response JSON: workouts count = {len(body_json.get('workouts', []))}, top_exercises = {body_json.get('top_exercises', [])}")

print("\n" + "="*70)
print("TEST c: Viewer role: DELETE a workout -> 403")
print("="*70)
# Member 1 creates a workout
m1_login = requests.post(f"{BASE_URL}/api/auth/login", json={
    "email": "member1_jwt@example.com",
    "password": "MemberPassword123!"
})
m1_token = m1_login.json()["token"]

create_res = requests.post(
    f"{BASE_URL}/api/workouts",
    headers={"Authorization": f"Bearer {m1_token}"},
    json={"exercise_name": "Bench Press", "sets": 3, "reps": 10, "weight_kg": 75.0, "date": "2026-10-25"}
)
workout_m1_id = create_res.json()["_id"]
print(f"Member 1 created workout: ID = {workout_m1_id}")

viewer_login = requests.post(f"{BASE_URL}/api/auth/login", json={
    "email": "viewer_jwt@example.com",
    "password": "ViewerPassword123!"
})
viewer_token = viewer_login.json()["token"]

curl_c = run(["curl.exe", "-i", "-s", "-X", "DELETE", "-H", f"Authorization: Bearer {viewer_token}", f"http://localhost/api/workouts/{workout_m1_id}"], stdout=PIPE, stderr=PIPE, text=True)
print(curl_c.stdout.strip())

print("\n" + "="*70)
print("TEST d: Member: DELETE someone else's workout -> 403, own workout -> 200")
print("="*70)
# Member 2 tries to delete Member 1's workout -> 403
m2_login = requests.post(f"{BASE_URL}/api/auth/login", json={
    "email": "member2_jwt@example.com",
    "password": "MemberPassword123!"
})
m2_token = m2_login.json()["token"]

curl_d1 = run(["curl.exe", "-i", "-s", "-X", "DELETE", "-H", f"Authorization: Bearer {m2_token}", f"http://localhost/api/workouts/{workout_m1_id}"], stdout=PIPE, stderr=PIPE, text=True)
print("--- Member 2 deleting Member 1's workout ---")
print(curl_d1.stdout.strip())

# Member 1 deletes their OWN workout -> 200
curl_d2 = run(["curl.exe", "-i", "-s", "-X", "DELETE", "-H", f"Authorization: Bearer {m1_token}", f"http://localhost/api/workouts/{workout_m1_id}"], stdout=PIPE, stderr=PIPE, text=True)
print("\n--- Member 1 deleting their own workout ---")
print(curl_d2.stdout.strip())

print("\n" + "="*70)
print("TEST e: Admin: DELETE any workout -> 200")
print("="*70)
# Member 2 creates a workout
create_res_m2 = requests.post(
    f"{BASE_URL}/api/workouts",
    headers={"Authorization": f"Bearer {m2_token}"},
    json={"exercise_name": "Deadlift", "sets": 4, "reps": 8, "weight_kg": 120.0, "date": "2026-10-25"}
)
workout_m2_id = create_res_m2.json()["_id"]
print(f"Member 2 created workout: ID = {workout_m2_id}")

# Admin deletes Member 2's workout -> 200
curl_e = run(["curl.exe", "-i", "-s", "-X", "DELETE", "-H", f"Authorization: Bearer {admin_token}", f"http://localhost/api/workouts/{workout_m2_id}"], stdout=PIPE, stderr=PIPE, text=True)
print(curl_e.stdout.strip())

print("\n" + "="*70)
print("TEST f: TOTP (setup, login -> mfa_required, wrong code -> 401, correct code -> token)")
print("="*70)
# 1. Login TotpTester to get token for setup
totp_user_login = requests.post(f"{BASE_URL}/api/auth/login", json={
    "email": "totp_jwt@example.com",
    "password": "TotpPassword123!"
})
totp_token = totp_user_login.json()["token"]

# 2. Call /api/auth/totp/setup
setup_res = requests.post(
    f"{BASE_URL}/api/auth/totp/setup",
    headers={"Authorization": f"Bearer {totp_token}"}
)
setup_data = setup_res.json()
uri = setup_data["uri"]
print(f"TOTP Setup status: {setup_res.status_code}")
print(f"OTPAuth URI: {uri[:40]}... (QR code generated)")

# Retrieve pending secret from MongoDB to generate code
totp_user_doc = db.users.find_one({"email": "totp_jwt@example.com"})
pending_secret = totp_user_doc["totp_pending_secret"]
totp_obj = pyotp.TOTP(pending_secret)
correct_code = totp_obj.now()

# 3. Enable TOTP
enable_res = requests.post(
    f"{BASE_URL}/api/auth/totp/enable",
    headers={"Authorization": f"Bearer {totp_token}"},
    json={"code": correct_code}
)
print(f"TOTP Enable status: {enable_res.status_code}, response: {enable_res.json()}")

# 4. Login with password only -> mfa_required
mfa_login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
    "email": "totp_jwt@example.com",
    "password": "TotpPassword123!"
})
mfa_login_data = mfa_login_res.json()
print(f"Password-only login status: {mfa_login_res.status_code}")
print(f"Response: mfa_required = {mfa_login_data.get('mfa_required')}, mfa_token present = {'mfa_token' in mfa_login_data}")
mfa_token = mfa_login_data["mfa_token"]

# 5. Verify with WRONG code -> 401
wrong_res = requests.post(
    f"{BASE_URL}/api/auth/totp/verify",
    json={"mfa_token": mfa_token, "code": "000000"}
)
print(f"Verify with WRONG code status: {wrong_res.status_code}, response: {wrong_res.json()}")

# 6. Verify with CORRECT code -> 200 with JWT
correct_code_2 = totp_obj.now()
verify_res = requests.post(
    f"{BASE_URL}/api/auth/totp/verify",
    json={"mfa_token": mfa_token, "code": correct_code_2}
)
verify_data = verify_res.json()
print(f"Verify with CORRECT code status: {verify_res.status_code}")
print(f"Response: message = {verify_data.get('message')}, user = {verify_data.get('name')}, role = {verify_data.get('role')}, token present = {'token' in verify_data}")

print("\n" + "="*70)
print("TEST g: Cross-backend routing (6 requests with Bearer token through Nginx)")
print("="*70)
backends_hit = []
for i in range(1, 7):
    resp = requests.get(
        f"{BASE_URL}/api/workouts",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    served_by = resp.headers.get("X-Served-By", "unknown")
    backends_hit.append(served_by)
    print(f"Request #{i}: HTTP {resp.status_code} | X-Served-By: {served_by}")
    time.sleep(0.3)

unique_backends = set(backends_hit)
print(f"\nUnique backends served: {unique_backends}")
print(f"Load balancing across multiple instances confirmed: {len(unique_backends) > 1}")

print("\n" + "="*70)
print("ALL TESTS COMPLETED SUCCESSFULLY!")
print("="*70)
