import sys
import os
from dotenv import load_dotenv
from pymongo import MongoClient

def main():
    if len(sys.argv) < 3:
        print("Usage: python set_role.py <username_or_email> <admin|member|viewer>")
        sys.exit(1)

    username_or_email = sys.argv[1].strip()
    role = sys.argv[2].strip().lower()

    if role not in ["admin", "member", "viewer"]:
        print("Error: Role must be one of 'admin', 'member', or 'viewer'.")
        sys.exit(1)

    load_dotenv()
    mongo_uri = os.environ.get("MONGO_URI")
    if not mongo_uri:
        print("Error: MONGO_URI not found in .env")
        sys.exit(1)

    client = MongoClient(mongo_uri)
    try:
        db = client.get_default_database()
        if db is None:
            db = client["fitness_tracker"]
    except Exception:
        db = client["fitness_tracker"]

    user = db.users.find_one({
        "$or": [
            {"name": username_or_email},
            {"email": username_or_email},
            {"name": {"$regex": f"^{username_or_email}$", "$options": "i"}},
            {"email": {"$regex": f"^{username_or_email}$", "$options": "i"}}
        ]
    })

    if not user:
        print(f"Error: User '{username_or_email}' not found.")
        sys.exit(1)

    db.users.update_one({"_id": user["_id"]}, {"$set": {"role": role}})
    name = user.get("name") or user.get("email")
    print(f"Successfully updated role for user '{name}' ({user.get('email')}) to '{role}'.")

if __name__ == "__main__":
    main()
