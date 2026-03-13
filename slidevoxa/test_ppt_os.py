import requests

url_base = 'http://localhost:8000/api/presentations'

print("--- UPLOADING ---")
files = {'file': ('test.pptx', open(r'c:\Users\yemin\OneDrive\文档\MongoDB_Atlas_Conn\venv\Lib\site-packages\pptx\templates\default.pptx', 'rb'), 'application/vnd.openxmlformats-officedocument.presentationml.presentation')}
data = {'user_id': 'tester', 'user_email': 'test@test.com'}
res = requests.post(f"{url_base}/upload", files=files, data=data)
print("UPLOAD:", res.status_code, res.text)
