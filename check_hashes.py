import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient

def main():
    load_dotenv()
    mongo_uri = os.environ.get("MONGO_URI")
    if not mongo_uri:
        print("ERROR: MONGO_URI not found in .env", file=sys.stderr)
        sys.exit(1)

    client = MongoClient(mongo_uri)
    try:
        db = client.get_default_database()
        if db is None:
            db = client["fitness_tracker"]
    except Exception:
        db = client["fitness_tracker"]

    users = list(db.users.find({}, {"name": 1, "email": 1, "password": 1}))
    if not users:
        print("No users found in database.")
        return

    print("=" * 55)
    print(f"{'Username':<30} | {'Hash Prefix (first 7)':<20}")
    print("-" * 55)
    for u in users:
        username = u.get("name") or u.get("email") or "Unknown"
        pw_hash = u.get("password") or ""
        prefix = pw_hash[:7] if len(pw_hash) >= 7 else pw_hash
        print(f"{username:<30} | {prefix:<20}")
    print("=" * 55)

if __name__ == "__main__":
    main()
