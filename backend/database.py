import os
import certifi
from pymongo import MongoClient
import gridfs
from dotenv import load_dotenv

# Load .env from parent directory (Repository Root)
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(_env_path)

MONGO_URL = os.getenv("MongoDB_URL")

# Debugging on Render logs
if not MONGO_URL:
    print("WARNING: MongoDB_URL not found in environment variables!")
else:
    # Print a masked version of the URL to verify it's loaded
    masked_url = MONGO_URL.split("@")[-1] if "@" in MONGO_URL else "URL-Found-But-Malformed"
    print(f"DEBUG: Attempting to connect to MongoDB at: ...@{masked_url}")

# Explicitly use certifi version of root certificates for SSL/TLS
# Added connectTimeoutMS and appName for better diagnostics
client = MongoClient(
    MONGO_URL, 
    tlsCAFile=certifi.where(),
    connectTimeoutMS=20000,
    serverSelectionTimeoutMS=20000,
    appName="SlideVoxa_Render"
)
db = client["slidevoxa_db"]
fs = gridfs.GridFS(db)

# Collections
presentations_col = db["presentations"]
users_col = db["users"]
sessions_col = db["sessions"]
media_col = db["media"]

# Create indexes for performance
presentations_col.create_index("user_id")
users_col.create_index("email", unique=True)
media_col.create_index([("presentation_id", 1), ("slide_number", 1)])
