import os
import boto3

# Import FastAPI and related modules
from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException, BackgroundTasks 
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

# Import List for type hinting
from typing import List

# Import uuid for generating unique file IDs
import uuid

# Import time for delay functionality
import time
from datetime import datetime

# Logging setup
import logging
logger = logging.getLogger(__name__)

# Load environment variable
from dotenv import load_dotenv
load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME")

# Fast API setup 
app = FastAPI()

# Allow CORS for frontend (adjust the origin as needed)
app.add_middleware(
    CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
)

# Initialize clients
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
        file_id = str(uuid.uuid4())

        click_status = {email: False for email in emails}
        
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key= file_id,
            Body=content
        )

        dynamo_table.put_item(
            Item={
                "FileId": file_id,
                "FileName": file.filename,
                "Emails": emails,
                "ClickStatus": click_status,
                "Upload_timestamp": datetime.utcnow().isoformat(),
                "Deleted": False
            }
        )

        return {
            "message": "File uploaded successfully to S3 and metadata stored in DynamoDB.",
            "filename": file.filename,
            "status": 200
        }

    except Exception as e:
        logger.exception(f"Error uploading file: {str(e)}")
        return {"error": f"Failed to upload file: {str(e)}"}


# Download file, check clicked status and delete the file from S3 bucket
def get_file_record(file_id: str):
    try:
        response = dynamo_table.get_item(Key={"FileId": file_id})
        return response.get("Item")
    except Exception as e:
        logger.exception(f"Error generating pre-signed URL: {str(e)}")
        return HTTPException(status_code=404, detail="File not found.")

def generate_file_url(s3_key: str, original_filename: str):
    try:
        return s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET_NAME, 'Key': s3_key, 'ResponseContentDisposition': f'attachment; filename="{original_filename}"'},
            ExpiresIn=3600
        )
    except Exception as e:
        logger.exception(f"[ERROR] Error generating pre-signed URL: {str(e)}")
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
        logger.exception(f"[ERROR] Failed to update click status for {email}: {e}")

def update_delete_status(file_id):
    try:
        dynamo_table.update_item(
            Key={"FileId": file_id},
            UpdateExpression="SET #d = :true",
            ExpressionAttributeNames={"#d": "Deleted"},
            ExpressionAttributeValues={":true": True}
        )
    except Exception as e:
        logger.exception(f"[ERROR] Failed to update delete status for {file_id}: {e}")

def check_and_delete_file_later(file_id: str, delay_seconds: int = 5) :
    time.sleep(delay_seconds)
    logger.info(f"[DELETE] File delete process started for {file_id}")
    
    file_record = get_file_record(file_id)
    
    if not file_record:
        return
    
    if all(file_record["ClickStatus"].values()):
        logger.info(f"[DELETE] All users have clicked the link for {file_id}")
        try: 
            update_delete_status(file_id)
            s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=file_id)
            logger.info(f"[DELETE] File {file_id} deleted successfully")
        except Exception as e:
            logger.exception(f"[ERROR] Failed to delete file {file_id}: {e}")

@app.get("/download/{fileid}")
def download_file(fileid: str, background_tasks: BackgroundTasks, email: str = Query(...)):
    if not fileid or not email:
        raise HTTPException(status_code=400, detail="You dont have access to this file.")
    
    file_record = get_file_record(fileid)

    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    if email not in file_record["Emails"]:
        raise HTTPException(status_code=403, detail="Unauthorized user")
    
    update_user_click(fileid, email)

    original_filename = file_record.get("FileName")

    download_url = generate_file_url(fileid, original_filename)
    if not download_url:
        raise HTTPException(status_code=500, detail="Could not generate download link")
    
    background_tasks.add_task(check_and_delete_file_later, fileid)
    
    return RedirectResponse(url=download_url)

