from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List

app = FastAPI()

# Allow CORS for frontend (adjust the origin as needed)
app.add_middleware(
    CORSMiddleware,
       allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.1.163:3000"  # 👈 Add your actual frontend IP here
    ],  # frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/upload/")
async def upload(file: UploadFile = File(...), emails: List[str] = Form(...)):
    content = await file.read()
    print(f"File name: {file.filename}, size: {len(content)} bytes")
    print("Emails received:", emails)
    return {"message": "File and emails received"}
