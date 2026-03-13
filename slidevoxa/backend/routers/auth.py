import hashlib
import uuid
import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.database import users_col

router = APIRouter(prefix="/api/auth", tags=["auth"])

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

class LoginRequest(BaseModel):
    email: str
    password: str

class SocialLoginRequest(BaseModel):
    uid: str
    email: str
    name: str = ""
    photo_url: str = ""

class RegisterRequest(BaseModel):
    name: str = ""
    email: str
    password: str

@router.post("/register")
def register_user(req: RegisterRequest):
    req.email = req.email.strip().lower()
    existing = users_col.find_one({"email": req.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")
    
    user_id = str(uuid.uuid4())
    doc = {
        "_id": user_id,
        "email": req.email,
        "password_hash": hash_password(req.password),
        "display_name": req.name.strip(),
        "photo_url": "",
        "created_at": datetime.datetime.utcnow().isoformat()
    }
    users_col.insert_one(doc)
    return {"uid": user_id, "email": req.email, "display_name": req.name.strip(), "photo_url": ""}

@router.post("/login")
def login_user(req: LoginRequest):
    req.email = req.email.strip().lower()
    user = users_col.find_one({
        "email": req.email,
        "password_hash": hash_password(req.password)
    })
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    
    return {
        "uid": str(user["_id"]),
        "email": user["email"],
        "display_name": user.get("display_name", ""),
        "photo_url": user.get("photo_url", "")
    }

@router.post("/social-login")
def social_login(req: SocialLoginRequest):
    req.email = req.email.strip().lower()
    # Find by email if UID is not a string ID? Or just find by UID.
    # Firebase UID is a string, we use it as our _id.
    user = users_col.find_one({"_id": req.uid})
    if not user:
        # Check if email exists first from standard registration
        user_by_email = users_col.find_one({"email": req.email})
        if user_by_email:
            # Update user info if missing
            update_fields = {}
            if req.name and not user_by_email.get("display_name"):
                update_fields["display_name"] = req.name.strip()
            if req.photo_url and not user_by_email.get("photo_url"):
                update_fields["photo_url"] = req.photo_url
            
            if update_fields:
                users_col.update_one({"_id": user_by_email["_id"]}, {"$set": update_fields})
                user_by_email.update(update_fields)

            return {
                "uid": str(user_by_email["_id"]),
                "email": user_by_email["email"],
                "display_name": user_by_email.get("display_name", ""),
                "photo_url": user_by_email.get("photo_url", "")
            }

        # Create user
        user_doc = {
            "_id": req.uid,
            "email": req.email,
            "display_name": req.name.strip(),
            "photo_url": req.photo_url,
            "created_at": datetime.datetime.utcnow().isoformat()
        }
        users_col.insert_one(user_doc)
        user = user_doc
    else:
        # Update name and photo if they came from social login
        update_fields = {}
        if req.name and not user.get("display_name"):
            update_fields["display_name"] = req.name.strip()
        if req.photo_url and not user.get("photo_url"):
            update_fields["photo_url"] = req.photo_url
        
        if update_fields:
            users_col.update_one({"_id": req.uid}, {"$set": update_fields})
            user.update(update_fields)

    return {
        "uid": str(user.get("_id", req.uid)),
        "email": req.email,
        "display_name": user.get("display_name", ""),
        "photo_url": user.get("photo_url", "")
    }

@router.get("/user/{uid}")
def get_user(uid: str) -> dict:
    doc = users_col.find_one({"_id": uid})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found.")
    doc["id"] = str(doc.pop("_id", ""))
    return doc
