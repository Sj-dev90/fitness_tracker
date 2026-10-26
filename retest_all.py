import os
import sys
import json
import base64
import io
import requests
import pyotp
from subprocess import run, PIPE

BASE_URL = "http://localhost"

print("=" * 70)
print("COMPREHENSIVE POST-REBUILD VERIFICATION TEST")
print("=" * 70)

# 1. Check docker compose ps
print("\n[1] Checking docker compose ps:")
ps_res = run(["docker", "compose", "ps"], stdout=PIPE, stderr=PIPE, text=True)
print(ps_res.stdout.strip())

# 2. Health check through Nginx
print("\n[2] Checking /health through Nginx:")
h_res = requests.get(f"{BASE_URL}/health")
print(f"Status: {h_res.status_code}")
print(f"Body:   {h_res.text.strip()}")
assert h_res.status_code == 200, "Health check failed"

# 3. Normal login
print("\n[3] Testing Normal Login:")
test_email = "member1_jwt@example.com"
test_pass = "MemberPassword123!"

# Register or login
login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
    "email": test_email,
    "password": test_pass
})
if login_res.status_code == 401 or login_res.status_code == 404:
    # Register if not exists
    reg = requests.post(f"{BASE_URL}/api/auth/register", json={
        "name": "MemberOne",
        "email": test_email,
        "password": test_pass
    })
    print(f"Registered test user: {reg.status_code}")
    login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": test_email,
        "password": test_pass
    })

print(f"Login status: {login_res.status_code}")
login_data = login_res.json()
member_token = login_data.get("token")
print(f"Normal login success! User: {login_data.get('name')}, Role: {login_data.get('role')}, Got Token: {bool(member_token)}")
assert member_token, "No access token received for normal login"

# 4. TOTP Setup & QR code endpoint (verifying Pillow generation)
print("\n[4] Testing TOTP Setup & QR Code Endpoint (Pillow):")
totp_user_email = "totp_retest@example.com"
totp_user_pass = "TotpPassword123!"

# Ensure user exists
requests.post(f"{BASE_URL}/api/auth/register", json={
    "name": "TotpRetestUser",
    "email": totp_user_email,
    "password": totp_user_pass
})
t_login = requests.post(f"{BASE_URL}/api/auth/login", json={
    "email": totp_user_email,
    "password": totp_user_pass
})
t_token = t_login.json().get("token")
if not t_token:
    # Maybe 2FA was already enabled, test setup with member user
    t_token = member_token

setup_res = requests.post(f"{BASE_URL}/api/auth/totp/setup", headers={
    "Authorization": f"Bearer {t_token}"
})
print(f"TOTP Setup status: {setup_res.status_code}")
setup_data = setup_res.json()
uri = setup_data.get("uri")
qr_b64 = setup_data.get("qr_code")
print(f"URI received: {uri[:40]}...")
print(f"QR Code Base64 length: {len(qr_b64)} chars")

# Validate QR code with PIL
from PIL import Image
qr_bytes = base64.b64decode(qr_b64)
qr_img = Image.open(io.BytesIO(qr_bytes))
print(f"Pillow decoded QR image successfully: Format={qr_img.format}, Size={qr_img.size}, Mode={qr_img.mode}")
assert qr_img.format == "PNG", "QR image is not a PNG"

# Extract secret from URI and enable TOTP
import urllib.parse
parsed = urllib.parse.urlparse(uri)
qs = urllib.parse.parse_qs(parsed.query)
secret = qs['secret'][0]
totp = pyotp.TOTP(secret)
code = totp.now()

enable_res = requests.post(f"{BASE_URL}/api/auth/totp/enable", headers={
    "Authorization": f"Bearer {t_token}"
}, json={"code": code})
print(f"TOTP Enable status: {enable_res.status_code}, response: {enable_res.json()}")
assert enable_res.status_code == 200, "Failed to enable TOTP"

# 5. 2FA Login with TOTP test account
print("\n[5] Testing 2FA Login with TOTP:")
# Step A: Submit username/password -> should receive 200 with mfa_required
mfa_step1 = requests.post(f"{BASE_URL}/api/auth/login", json={
    "email": totp_user_email if t_token != member_token else test_email,
    "password": totp_user_pass if t_token != member_token else test_pass
})
print(f"MFA Login Step 1 status: {mfa_step1.status_code}")
mfa_step1_data = mfa_step1.json()
print(f"MFA required: {mfa_step1_data.get('mfa_required')}")
mfa_token = mfa_step1_data.get("mfa_token")
assert mfa_token, "No mfa_token returned"

# Step B: Submit TOTP code with mfa_token -> full access token
valid_code = totp.now()
mfa_step2 = requests.post(f"{BASE_URL}/api/auth/totp/verify", json={
    "mfa_token": mfa_token,
    "code": valid_code
})
print(f"MFA Login Step 2 status: {mfa_step2.status_code}")
mfa_step2_data = mfa_step2.json()
mfa_access_token = mfa_step2_data.get("token")
print(f"2FA Authenticated: {mfa_step2_data.get('message')}, Got final token: {bool(mfa_access_token)}")
assert mfa_access_token, "2FA verification did not return access token"

# 6. Workouts CRUD: POST, GET, DELETE
print("\n[6] Testing Workouts CRUD:")
auth_headers = {"Authorization": f"Bearer {mfa_access_token}"}

# POST Workout
new_workout_payload = {
    "exercise_name": "Hardened Bench Press",
    "sets": 4,
    "reps": 10,
    "weight_kg": 85.0,
    "date": "2026-10-25"
}
post_w = requests.post(f"{BASE_URL}/api/workouts", headers=auth_headers, json=new_workout_payload)
print(f"POST /api/workouts status: {post_w.status_code}")
post_w_data = post_w.json()
workout_id = post_w_data.get("workout", {}).get("_id") or post_w_data.get("id") or post_w_data.get("_id")
print(f"Created workout ID: {workout_id}")
assert post_w.status_code in (200, 201), "POST workout failed"

# GET Workouts
get_w = requests.get(f"{BASE_URL}/api/workouts", headers=auth_headers)
print(f"GET /api/workouts status: {get_w.status_code}")
workouts_list = get_w.json()
if isinstance(workouts_list, dict):
    workouts_list = workouts_list.get("workouts", [])
print(f"Total workouts retrieved: {len(workouts_list)}")
found = any(w.get("exercise_name") == "Hardened Bench Press" for w in workouts_list)
print(f"Found created workout in GET response: {found}")
assert found, "Created workout not found in GET response"

# Find actual ID if not captured from POST
if not workout_id:
    for w in workouts_list:
        if w.get("exercise_name") == "Hardened Bench Press":
            workout_id = w.get("_id")
            break

# DELETE Workout
del_w = requests.delete(f"{BASE_URL}/api/workouts/{workout_id}", headers=auth_headers)
print(f"DELETE /api/workouts/{workout_id} status: {del_w.status_code}")
print(f"DELETE response: {del_w.json()}")
assert del_w.status_code == 200, "DELETE workout failed"

# Verify deletion
get_after = requests.get(f"{BASE_URL}/api/workouts", headers=auth_headers)
w_after = get_after.json()
if isinstance(w_after, dict):
    w_after = w_after.get("workouts", [])
still_present = any(w.get("_id") == workout_id for w in w_after)
print(f"Workout still present after delete: {still_present}")
assert not still_present, "Workout was not deleted"

print("\n" + "=" * 70)
print("ALL TESTS PASSED SUCCESSFULLY!")
print("=" * 70)
