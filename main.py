import os
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import boto3
from typing import List
from datetime import datetime

# Load environment variable
load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME")

app = FastAPI()

# Allow CORS for frontend (adjust the origin as needed)
app.add_middleware(
    CORSMiddleware,
       allow_origins=[
        "https://file-sharing-app-nine-lime.vercel.app",
    ],  # frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/upload/")
async def upload(file: UploadFile = File(...), emails: List[str] = Form(...)):
    content = await file.read()
    try:
        print(f"File name: {file.filename}, size: {len(content)} bytes")
        print("Emails received:", emails)
        
        # Initialize S3 client
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )

        dynamodb = boto3.resource(
        "dynamodb",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
        )
        dynamo_table = dynamodb.Table(DYNAMODB_TABLE_NAME)

        # Upload to S3
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=file.filename,
            Body=content
        )

        # Save metadata to DynamoDB
        dynamo_table.put_item(
            Item={
                "filename": file.filename,
                "emails": emails,
            }
        )

        return {
            "message": "File uploaded successfully to S3 and metadata stored in DynamoDB.",
            "filename": file.filename,
            "status": 200
        }

    except Exception as e:
        print(f"Error uploading file: {str(e)}")
        return {"error": f"Failed to upload file: {str(e)}"}
