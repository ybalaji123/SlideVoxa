from slidevoxa.backend.database import presentations_col, media_col
import sys

# Windows encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

pres_id = sys.argv[1] if len(sys.argv) > 1 else None

if not pres_id:
    print("Recent presentations:")
    for p in presentations_col.find().sort("created_at", -1).limit(5):
        print(f"ID: {p['_id']}, Title: {p['title']}, Status: {p['status']}")
else:
    p = presentations_col.find_one({"_id": pres_id})
    if p:
        print(f"Presentation: {p['title']}")
        print(f"Status: {p['status']}")
        print(f"Slide Count: {p['slide_count']}")
        
        media_count = media_col.count_documents({"presentation_id": pres_id})
        print(f"Media count: {media_count}")
        
        for m in media_col.find({"presentation_id": pres_id}).limit(5):
            has_img = "YES" if m.get("image_data_uri") else "NO"
            has_audio = "YES" if m.get("audio_data_uri") else "NO"
            print(f"  Slide {m['slide_number']}: Image={has_img}, Audio={has_audio}")
    else:
        print("Not found")
