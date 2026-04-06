import asyncio
import json

import boto3
from boto3.dynamodb.conditions import Key

from app.config import settings
from app.models.performance import VideoPerformance
from app.models.pipeline import PipelineRun


class DynamoClient:
    def __init__(self):
        self._dynamo = boto3.resource("dynamodb", region_name=settings.aws_region)
        self._runs_table = self._dynamo.Table(settings.dynamodb_runs_table)
        self._perf_table = self._dynamo.Table(settings.dynamodb_perf_table)

    async def create_run(self, run: PipelineRun) -> None:
        item = json.loads(run.model_dump_json())
        await asyncio.to_thread(self._runs_table.put_item, Item=item)

    async def get_run(self, run_id: str) -> PipelineRun | None:
        response = await asyncio.to_thread(
            self._runs_table.get_item,
            Key={"run_id": run_id},
        )
        item = response.get("Item")
        return PipelineRun.model_validate(item) if item is not None else None

    async def update_run_status(self, run_id: str, status: str, **fields) -> None:
        update_parts = ["#s = :s"]
        expr_names: dict[str, str] = {"#s": "status"}
        expr_values: dict[str, str] = {":s": status}

        for k, v in fields.items():
            placeholder = f"#{k}"
            value_placeholder = f":{k}"
            update_parts.append(f"{placeholder} = {value_placeholder}")
            expr_names[placeholder] = k
            expr_values[value_placeholder] = v

        await asyncio.to_thread(
            self._runs_table.update_item,
            Key={"run_id": run_id},
            UpdateExpression="SET " + ", ".join(update_parts),
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )

    async def list_runs_by_session(self, session_id: str) -> list[PipelineRun]:
        response = await asyncio.to_thread(
            self._runs_table.query,
            IndexName="session_id-index",
            KeyConditionExpression=Key("session_id").eq(session_id),
        )
        return [PipelineRun.model_validate(item) for item in response.get("Items", [])]

    async def put_performance(self, perf: VideoPerformance) -> None:
        item = json.loads(perf.model_dump_json())
        await asyncio.to_thread(self._perf_table.put_item, Item=item)

    async def get_performance(self, run_id: str) -> list[VideoPerformance]:
        response = await asyncio.to_thread(
            self._perf_table.query,
            KeyConditionExpression=Key("run_id").eq(run_id),
        )
        return [VideoPerformance.model_validate(item) for item in response.get("Items", [])]
