import json
import boto3
from botocore.exceptions import ClientError

# Clients
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')  # ✅ You missed this earlier
ses = boto3.client('ses')

# Your bucket name
S3_BUCKET_NAME = "project-file-sharing-app"

def generate_presigned_url(bucket_name, object_key, expiration=3600):
    try:
        response = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': object_key},
            ExpiresIn=expiration
        )
        print("Generated pre-signed URL:", response)
        return response
    except Exception as e:
        print(f"Error generating pre-signed URL: {str(e)}")
        return None

def lambda_handler(event, context):
    record = event['Records'][0]
    object_key = record['s3']['object']['key']
    print(f"Triggered by file: {object_key}")

    # DynamoDB table
    table = dynamodb.Table('fileEmail')

    try:
        response = table.get_item(Key={"filename": object_key})
        item = response.get("Item")
        if not item:
            print(f"No email entry found in DynamoDB for file: {object_key}")
            return {"statusCode": 404, "body": "No emails found"}

        emails = item.get("emails", [])
        print(f"Emails for {object_key}: {emails}")

        # Generate link
        subject = f"File Available: {object_key}"
        file_link = generate_presigned_url(S3_BUCKET_NAME, object_key)
        if not file_link:
            return {"statusCode": 500, "body": "Failed to generate pre-signed URL"}

        body_html = f"""
        <!DOCTYPE html>
        <html>
        <body>
            <p>Hello,</p>
            <p>A file has been uploaded and is available to download for 1 hour.</p>
            <p><a href="{file_link}">Click here to download {object_key}</a></p>
            <p>Thanks,<br>File Sharing App</p>
            
        </body>
        </html>
        """ 

        response = ses.send_email(
            Source='harshapatel112003@gmail.com',
            Destination={'ToAddresses': emails},
            Message={
                'Subject': {
                    'Charset': 'UTF-8',
                    'Data': subject,
                },
                'Body': {
                    'Html': {
                        'Data': body_html,
                        'Charset': 'UTF-8'
                    }
                },
            }
        )

        print(f"Email sent. Message ID: {response['MessageId']}")
        return {
            'statusCode': 200,
            'body': json.dumps("Email sent successfully.")
        }

    except ClientError as e:
        print(f"Error sending email: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps("Failed to send email.")
        }

    except Exception as e:
        print(f"Error fetching emails from DynamoDB: {str(e)}")
        return {"statusCode": 500, "body": str(e)}
