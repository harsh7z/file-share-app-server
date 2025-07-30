import os
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException, BackgroundTasks 
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import boto3
from typing import List
from datetime import datetime
import uuid
import time

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
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
)

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

#Uplode file to s3 and store the data to dynamodb
@app.post("/upload/")
async def upload(file: UploadFile = File(...), emails: List[str] = Form(...)):
    content = await file.read()
    try:
        # Generate a unique FileID (UUID) for your file record
        file_id = str(uuid.uuid4())

        # Initialize click_status map: all emails set to False (not clicked yet)
        click_status = {email: False for email in emails}
        
        # Upload to S3
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key= file_id,
            Body=content
        )

        # Save metadata to DynamoDB
        dynamo_table.put_item(
            Item={
                "FileId": file_id,
                "FileName": file.filename,
                "Emails": emails,
                "ClickStatus": click_status,
                "Upload_timestamp": datetime.utcnow().isoformat(),
                "Delete": False
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


#File Download
def get_file_record(file_id: str):
    try:
        response = dynamo_table.get_item(Key={"FileId": file_id})
        return response.get("Item")
    except Exception as e:
        print(f"Error generating pre-signed URL: {str(e)}")
        return HTTPException(status_code=404, detail="File not found.")

def generate_file_url(s3_key: str, original_filename: str):
    try:
        return s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET_NAME, 'Key': s3_key, 'ResponseContentDisposition': f'attachment; filename="{original_filename}"'},
            ExpiresIn=3600
        )
    except Exception as e:
        print(f"Error generating pre-signed URL: {str(e)}")
        return None

def update_user_click(file_id: str, email: str):
    try:
        dynamo_table.update_item(
            Key={"FileId": file_id},
            UpdateExpression="SET ClickStatus.#email = :val",
            ExpressionAttributeNames={"#email": email},
            ExpressionAttributeValues={":val": True}
        )
    except Exception as e:
        print(f"Failed to update click status for {email}: {e}")

def update_delete_status(file_id):
    try:
        dynamo_table.update_item(
            Key={"FileId": file_id},
            UpdateExpression="SET #d = :true",
            ExpressionAttributeNames={"#d": "Delete"},
            ExpressionAttributeValues={":true": True}
        )
    except Exception as e:
        print(f"Failed to update delete status for {file_id}: {e}")

def check_and_delete_file_later(file_id: str, delay_seconds: int = 5) :
    time.sleep(delay_seconds)
    
    file_record = get_file_record(file_id)
    
    if not file_record:
        return
    
    if all(file_record["ClickStatus"].values()):
        update_delete_status(file_id)
        
    if file_record.get("Delete") == True:
        try:
            s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=file_id)
            print(f"File {file_id} deleted from S3.")
        except Exception as e:
            print(f"Failed to delete file {file_id}: {e}")

@app.get("/download/{fileid}")
def download_file(fileid: str, email: str = Query(...)):
    if not fileid or not email:
        raise HTTPException(status_code=400, detail="You dont have access to this file.")
    
    file_record = get_file_record(fileid)

    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    if email not in file_record["Emails"]:
        raise HTTPException(status_code=403, detail="Unauthorized user")
    
     # Mark user as clicked
    update_user_click(fileid, email)

    original_filename = file_record.get("FileName")

    if all(file_record["ClickStatus"].values()):
        update_delete_status(fileid)

        if file_record.get("Delete") == True:
            s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=fileid)
            print(f"[SUCCESS] File {fileid} deleted from S3.")

            
    # Generate pre-signed S3 URL
    download_url = generate_file_url(fileid)
    if not download_url:
        raise HTTPException(status_code=500, detail="Could not generate download link")


    return RedirectResponse(url=download_url)

