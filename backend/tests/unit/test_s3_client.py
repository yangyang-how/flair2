"""Unit tests for S3Client using moto."""

import asyncio

import boto3
import pytest
from moto import mock_aws

from app.config import settings


@pytest.fixture(autouse=True)
def s3_env(monkeypatch):
    monkeypatch.setattr(settings, "aws_region", "us-east-1")
    monkeypatch.setattr(settings, "s3_bucket", "test-bucket")


@mock_aws
def test_upload_and_download():
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")

    from app.infra.s3_client import S3Client

    client = S3Client()
    asyncio.run(client.upload_json("runs/run1/output.json", '{"result": "ok"}'))
    downloaded = asyncio.run(client.download_json("runs/run1/output.json"))
    assert downloaded == '{"result": "ok"}'


@mock_aws
def test_presigned_url():
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")

    from app.infra.s3_client import S3Client

    client = S3Client()
    asyncio.run(client.upload_json("runs/run1/file.json", "{}"))
    url = asyncio.run(client.generate_presigned_url("runs/run1/file.json", expires_in=300))
    assert "runs/run1/file.json" in url
    assert url.startswith("https://")
