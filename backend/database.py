import os
import certifi
from pymongo import MongoClient
import gridfs
from dotenv import load_dotenv

# Load .env from parent directory (Repository Root)
_env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(_env_path)

MONGO_URL = os.getenv("MongoDB_URL")

# Explicitly use certifi version of root certificates for SSL/TLS
client = MongoClient(MONGO_URL, tlsCAFile=certifi.where())
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
