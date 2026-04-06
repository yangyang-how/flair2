import asyncio

import boto3

from app.config import settings


class S3Client:
    def __init__(self):
        self._s3 = boto3.client("s3", region_name=settings.aws_region)
        self._bucket = settings.s3_bucket

    async def upload_json(self, key: str, data: str) -> None:
        await asyncio.to_thread(
            self._s3.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data.encode(),
            ContentType="application/json",
        )

    async def download_json(self, key: str) -> str:
        response = await asyncio.to_thread(
            self._s3.get_object,
            Bucket=self._bucket,
            Key=key,
        )
        body = response["Body"]
        content = await asyncio.to_thread(body.read)
        return content.decode()

    async def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        return await asyncio.to_thread(
            self._s3.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )
