"""Unit tests for DynamoClient using moto."""

import asyncio
from datetime import UTC, datetime

import boto3
import pytest
from moto import mock_aws

from app.config import settings
from app.models.performance import VideoPerformance
from app.models.pipeline import CreatorProfile, PipelineConfig, PipelineRun, PipelineStatus


@pytest.fixture(autouse=True)
def dynamo_env(monkeypatch):
    monkeypatch.setattr(settings, "aws_region", "us-east-1")
    monkeypatch.setattr(settings, "dynamodb_runs_table", "pipeline_runs")
    monkeypatch.setattr(settings, "dynamodb_perf_table", "video_performance")


def _make_tables():
    dynamo = boto3.resource("dynamodb", region_name="us-east-1")
    dynamo.create_table(
        TableName="pipeline_runs",
        KeySchema=[{"AttributeName": "run_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "run_id", "AttributeType": "S"},
            {"AttributeName": "session_id", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[{
            "IndexName": "session_id-index",
            "KeySchema": [{"AttributeName": "session_id", "KeyType": "HASH"}],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
        }],
        BillingMode="PAY_PER_REQUEST",
    )
    dynamo.create_table(
        TableName="video_performance",
        KeySchema=[
            {"AttributeName": "run_id", "KeyType": "HASH"},
            {"AttributeName": "script_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "run_id", "AttributeType": "S"},
            {"AttributeName": "script_id", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def _sample_run(run_id: str, session_id: str = "sess1") -> PipelineRun:
    return PipelineRun(
        run_id=run_id,
        session_id=session_id,
        status=PipelineStatus.PENDING,
        config=PipelineConfig(
            run_id=run_id,
            session_id=session_id,
            reasoning_model="kimi",
            creator_profile=CreatorProfile(
                tone="casual",
                vocabulary=[],
                catchphrases=[],
                topics_to_avoid=[],
            ),
        ),
        created_at=datetime.now(UTC),
    )


@mock_aws
def test_create_and_get_run():
    _make_tables()
    from app.infra.dynamo_client import DynamoClient

    client = DynamoClient()
    run = _sample_run("run-abc")
    asyncio.run(client.create_run(run))
    retrieved = asyncio.run(client.get_run("run-abc"))
    assert retrieved is not None
    assert retrieved.run_id == "run-abc"
    assert retrieved.status == PipelineStatus.PENDING


@mock_aws
def test_get_run_missing():
    _make_tables()
    from app.infra.dynamo_client import DynamoClient

    client = DynamoClient()
    assert asyncio.run(client.get_run("does-not-exist")) is None


@mock_aws
def test_update_run_status():
    _make_tables()
    from app.infra.dynamo_client import DynamoClient

    client = DynamoClient()
    run = _sample_run("run-upd")
    asyncio.run(client.create_run(run))
    asyncio.run(client.update_run_status("run-upd", "running", current_stage="S1_MAP"))
    retrieved = asyncio.run(client.get_run("run-upd"))
    assert retrieved.status == "running"


@mock_aws
def test_put_and_get_performance():
    _make_tables()
    from app.infra.dynamo_client import DynamoClient

    client = DynamoClient()
    perf = VideoPerformance(
        run_id="run-perf",
        script_id="script-1",
        platform="tiktok",
        post_url="https://tiktok.com/v/123",
        posted_at=datetime.now(UTC),
        views=1000,
        likes=50,
        comments=10,
        shares=5,
        committee_rank=1,
        script_pattern="hook+pacing",
    )
    asyncio.run(client.put_performance(perf))
    results = asyncio.run(client.get_performance("run-perf"))
    assert len(results) == 1
    assert results[0].script_id == "script-1"
    assert results[0].views == 1000
