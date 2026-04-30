import logging
import os

import boto3

AWS_REGION = "us-east-1"
S3_BUCKET = "tractuslabs-data-sources"

BEDROCK_ANTHROPIC_MODELS = {
    "sonnet-4-5": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "sonnet-4-6": "us.anthropic.claude-sonnet-4-6",
    "opus-4-5": "us.anthropic.claude-opus-4-5-20251101-v1:0",
    "opus-4-6": "us.anthropic.claude-opus-4-6-v1",
    "opus-4-7": "us.anthropic.claude-opus-4-7",
}

logger = logging.getLogger()
logger.setLevel(logging.INFO)

team_info = {
    "name": "Für Elise",
    "email": "van@beethonven.com",
    "phone": "+000000000000",
    "contact_point": "Van Beethoven",
}
customer_info = {
    "name": "Da Vinci",
    "email": "da@vinci.com",
    "id": "432eef62-3867-46b7-abf0-cdb2a09183d6",
}

def create_boto3_client(name: str, region: str = AWS_REGION):
    if os.getenv("IS_LOCAL", "") == "true":
        if name == "dynamodb":
            return boto3.resource(
                name,
                region_name=region,
                aws_access_key_id=os.getenv("ACCESS_KEY"),
                aws_secret_access_key=os.getenv("SECRET_KEY"),
            )
        return boto3.client(
            name,
            region_name=region,
            aws_access_key_id=os.getenv("ACCESS_KEY"),
            aws_secret_access_key=os.getenv("SECRET_KEY"),
        )
    else:
        return boto3.client(name, region_name=region)

