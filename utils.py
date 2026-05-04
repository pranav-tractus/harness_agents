import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

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
    "name": "Van Beethoven",
    "email": "van@beethonven.com",
    "phone": "+000000000000",
    "address": "123 Main St, Anytown, USA",
}
customer_info = {
    "name": "Leonardo da Vinci",
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


def setup_streamlit_console_logfile() -> Path:
    """Mirror console output to a timestamped logfile once per server process."""
    root_logger = logging.getLogger()
    if getattr(root_logger, "_streamlit_logfile_initialized", False):
        return getattr(root_logger, "_streamlit_logfile_path")

    logs_dir = Path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    logfile = logs_dir / f"streamlit-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"

    class _TeeStream:
        def __init__(self, *streams):
            self._streams = streams
            self._ansi_re = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

        def write(self, data):
            for stream in self._streams:
                if getattr(stream, "_strip_ansi", False):
                    stream.write(self._ansi_re.sub("", data))
                else:
                    stream.write(data)
                stream.flush()
            return len(data)

        def flush(self):
            for stream in self._streams:
                stream.flush()

        def isatty(self):
            return False

    log_file_handle = logfile.open("a", encoding="utf-8", buffering=1)
    log_file_handle._strip_ansi = True
    sys.stdout = _TeeStream(sys.__stdout__, log_file_handle)
    sys.stderr = _TeeStream(sys.__stderr__, log_file_handle)

    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    root_logger._streamlit_logfile_initialized = True
    root_logger._streamlit_logfile_path = logfile
    root_logger.info("Console logging initialized. Writing to %s", logfile.resolve())
    return logfile

