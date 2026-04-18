#!/usr/bin/env bash
# Import existing AWS resources into Terraform state.
#
# Use when state has drifted from reality — Terraform thinks nothing exists,
# but the resources are there in AWS. This discovers each resource by name/tag
# and imports it, so the next `terraform apply` becomes a no-op.
#
# Idempotent: resources already in state are skipped.
# Safe to run multiple times.
#
# Usage:
#   cd terraform
#   ../scripts/tf-import-existing.sh
#
# Environment:
#   PROJECT (default: flair2)
#   ENV     (default: dev)
#   REGION  (default: us-west-2)

set -eu

PROJECT="${PROJECT:-flair2}"
ENV="${ENV:-dev}"
REGION="${REGION:-us-west-2}"
PREFIX="${PROJECT}-${ENV}"
VAR_FILE="environments/${ENV}.tfvars"

echo "Terraform state import — ${PREFIX} in ${REGION}"
echo "============================================="

# ── Helper: import a resource, skipping if already in state ────────────────
tf_import() {
    local addr="$1"
    local id="$2"

    if [ -z "${id}" ] || [ "${id}" = "None" ] || [ "${id}" = "null" ]; then
        echo "[skip] ${addr} — AWS resource not found"
        return 0
    fi

    if terraform state list 2>/dev/null | grep -qxF "${addr}"; then
        echo "[already] ${addr}"
        return 0
    fi

    if terraform import -var-file="${VAR_FILE}" "${addr}" "${id}" >/dev/null 2>&1; then
        echo "[imported] ${addr} ← ${id}"
    else
        echo "[failed] ${addr} ← ${id}"
    fi
}

# ── Discovery helpers ──────────────────────────────────────────────────────
vpc_id_by_name() {
    aws ec2 describe-vpcs --region "${REGION}" \
        --filters "Name=tag:Name,Values=$1" \
        --query 'Vpcs[0].VpcId' --output text 2>/dev/null || echo ""
}

subnet_id_by_name() {
    aws ec2 describe-subnets --region "${REGION}" \
        --filters "Name=tag:Name,Values=$1" \
        --query 'Subnets[0].SubnetId' --output text 2>/dev/null || echo ""
}

sg_id_by_name() {
    aws ec2 describe-security-groups --region "${REGION}" \
        --filters "Name=group-name,Values=$1" \
        --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo ""
}

route_table_id_by_name() {
    aws ec2 describe-route-tables --region "${REGION}" \
        --filters "Name=tag:Name,Values=$1" \
        --query 'RouteTables[0].RouteTableId' --output text 2>/dev/null || echo ""
}

rt_association_id() {
    local rt_id="$1"
    local subnet_id="$2"
    aws ec2 describe-route-tables --region "${REGION}" \
        --route-table-ids "${rt_id}" \
        --query "RouteTables[0].Associations[?SubnetId=='${subnet_id}'].RouteTableAssociationId | [0]" \
        --output text 2>/dev/null || echo ""
}

eip_alloc_id_by_name() {
    aws ec2 describe-addresses --region "${REGION}" \
        --filters "Name=tag:Name,Values=$1" \
        --query 'Addresses[0].AllocationId' --output text 2>/dev/null || echo ""
}

nat_id_by_name() {
    aws ec2 describe-nat-gateways --region "${REGION}" \
        --filter "Name=tag:Name,Values=$1" "Name=state,Values=available" \
        --query 'NatGateways[0].NatGatewayId' --output text 2>/dev/null || echo ""
}

igw_id_for_vpc() {
    aws ec2 describe-internet-gateways --region "${REGION}" \
        --filters "Name=attachment.vpc-id,Values=$1" \
        --query 'InternetGateways[0].InternetGatewayId' --output text 2>/dev/null || echo ""
}

# ── Network layer (root main.tf) ───────────────────────────────────────────
echo ""
echo "── Network layer ──"
VPC_ID=$(vpc_id_by_name "${PREFIX}-vpc")
tf_import "aws_vpc.main" "${VPC_ID}"

tf_import "aws_subnet.public[0]" "$(subnet_id_by_name ${PREFIX}-public-1)"
tf_import "aws_subnet.public[1]" "$(subnet_id_by_name ${PREFIX}-public-2)"
tf_import "aws_subnet.private[0]" "$(subnet_id_by_name ${PREFIX}-private-1)"
tf_import "aws_subnet.private[1]" "$(subnet_id_by_name ${PREFIX}-private-2)"

tf_import "aws_internet_gateway.main" "$(igw_id_for_vpc ${VPC_ID})"
tf_import "aws_eip.nat" "$(eip_alloc_id_by_name ${PREFIX}-nat-eip)"
tf_import "aws_nat_gateway.main" "$(nat_id_by_name ${PREFIX}-nat)"

PUB_RT=$(route_table_id_by_name "${PREFIX}-public-rt")
PRV_RT=$(route_table_id_by_name "${PREFIX}-private-rt")
tf_import "aws_route_table.public" "${PUB_RT}"
tf_import "aws_route_table.private" "${PRV_RT}"

PUB_SN_1=$(subnet_id_by_name "${PREFIX}-public-1")
PUB_SN_2=$(subnet_id_by_name "${PREFIX}-public-2")
PRV_SN_1=$(subnet_id_by_name "${PREFIX}-private-1")
PRV_SN_2=$(subnet_id_by_name "${PREFIX}-private-2")
tf_import "aws_route_table_association.public[0]" "$(rt_association_id ${PUB_RT} ${PUB_SN_1})"
tf_import "aws_route_table_association.public[1]" "$(rt_association_id ${PUB_RT} ${PUB_SN_2})"
tf_import "aws_route_table_association.private[0]" "$(rt_association_id ${PRV_RT} ${PRV_SN_1})"
tf_import "aws_route_table_association.private[1]" "$(rt_association_id ${PRV_RT} ${PRV_SN_2})"

tf_import "aws_security_group.alb" "$(sg_id_by_name ${PREFIX}-alb-sg)"
tf_import "aws_security_group.ecs" "$(sg_id_by_name ${PREFIX}-ecs-sg)"
tf_import "aws_security_group.elasticache" "$(sg_id_by_name ${PREFIX}-elasticache-sg)"

# ── IAM module ─────────────────────────────────────────────────────────────
echo ""
echo "── IAM module ──"
tf_import "module.iam.aws_iam_role.ecs_execution" "${PREFIX}-ecs-execution-role"
tf_import "module.iam.aws_iam_role.ecs_task" "${PREFIX}-ecs-task-role"
tf_import "module.iam.aws_iam_role.lambda" "${PREFIX}-lambda-role"
# Role policies and attachments require role_name:policy_name format — try common ones
tf_import "module.iam.aws_iam_role_policy.ecs_execution_secrets" "${PREFIX}-ecs-execution-role:${PREFIX}-ecs-execution-secrets"
tf_import "module.iam.aws_iam_role_policy.ecs_task_ssm" "${PREFIX}-ecs-task-role:${PREFIX}-ecs-task-ssm"
tf_import "module.iam.aws_iam_role_policy.lambda_basic" "${PREFIX}-lambda-role:${PREFIX}-lambda-basic"
tf_import "module.iam.aws_iam_role_policy_attachment.ecs_execution_managed" \
    "${PREFIX}-ecs-execution-role/arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
tf_import "module.iam.aws_iam_role_policy_attachment.lambda_managed" \
    "${PREFIX}-lambda-role/arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

# ── ECR module ─────────────────────────────────────────────────────────────
echo ""
echo "── ECR module ──"
tf_import "module.ecr.aws_ecr_repository.api" "${PREFIX}-api"
tf_import "module.ecr.aws_ecr_repository.worker" "${PREFIX}-worker"
tf_import "module.ecr.aws_ecr_lifecycle_policy.api" "${PREFIX}-api"
tf_import "module.ecr.aws_ecr_lifecycle_policy.worker" "${PREFIX}-worker"

# ── DynamoDB module ────────────────────────────────────────────────────────
echo ""
echo "── DynamoDB module ──"
tf_import "module.dynamodb.aws_dynamodb_table.pipeline_runs" "${PREFIX}-pipeline-runs"
tf_import "module.dynamodb.aws_dynamodb_table.video_performance" "${PREFIX}-video-performance"

# ── S3 module (data bucket) ────────────────────────────────────────────────
echo ""
echo "── S3 (data bucket) ──"
# The bucket name in the error log was "flair2-pipeline-dev" — different from prefix.
# Be tolerant: import whichever exists.
for bucket in "${PROJECT}-${ENV}-pipeline" "${PROJECT}-pipeline-${ENV}"; do
    if aws s3api head-bucket --bucket "${bucket}" --region "${REGION}" 2>/dev/null; then
        tf_import "module.s3.aws_s3_bucket.main" "${bucket}"
        tf_import "module.s3.aws_s3_bucket_public_access_block.main" "${bucket}"
        tf_import "module.s3.aws_s3_bucket_versioning.main" "${bucket}"
        tf_import "module.s3.aws_s3_bucket_lifecycle_configuration.main" "${bucket}"
        break
    fi
done

# ── Frontend module (S3 static site) ───────────────────────────────────────
echo ""
echo "── Frontend (S3 website) ──"
FE_BUCKET="${PREFIX}-frontend"
tf_import "module.frontend.aws_s3_bucket.frontend" "${FE_BUCKET}"
tf_import "module.frontend.aws_s3_bucket_website_configuration.frontend" "${FE_BUCKET}"
tf_import "module.frontend.aws_s3_bucket_public_access_block.frontend" "${FE_BUCKET}"
tf_import "module.frontend.aws_s3_bucket_policy.frontend" "${FE_BUCKET}"

# ── ElastiCache module ─────────────────────────────────────────────────────
echo ""
echo "── ElastiCache ──"
tf_import "module.elasticache.aws_elasticache_subnet_group.main" "${PREFIX}-redis-subnet-group"
tf_import "module.elasticache.aws_elasticache_cluster.main" "${PREFIX}-redis"

# ── ALB module ─────────────────────────────────────────────────────────────
echo ""
echo "── ALB ──"
ALB_ARN=$(aws elbv2 describe-load-balancers --region "${REGION}" \
    --query "LoadBalancers[?LoadBalancerName=='${PREFIX}-alb'].LoadBalancerArn" \
    --output text 2>/dev/null || echo "")
tf_import "module.alb.aws_lb.main" "${ALB_ARN}"

TG_ARN=$(aws elbv2 describe-target-groups --region "${REGION}" \
    --query "TargetGroups[?TargetGroupName=='${PREFIX}-api-tg'].TargetGroupArn" \
    --output text 2>/dev/null || echo "")
tf_import "module.alb.aws_lb_target_group.api" "${TG_ARN}"

if [ -n "${ALB_ARN}" ]; then
    HTTP_LISTENER=$(aws elbv2 describe-listeners --region "${REGION}" \
        --load-balancer-arn "${ALB_ARN}" \
        --query "Listeners[?Port==\`80\`].ListenerArn | [0]" \
        --output text 2>/dev/null || echo "")
    tf_import "module.alb.aws_lb_listener.http" "${HTTP_LISTENER}"
fi

# ── ECS module ─────────────────────────────────────────────────────────────
echo ""
echo "── ECS ──"
tf_import "module.ecs.aws_ecs_cluster.main" "${PREFIX}-cluster"

tf_import "module.ecs.aws_cloudwatch_log_group.api" "/ecs/${PREFIX}/api"
tf_import "module.ecs.aws_cloudwatch_log_group.worker" "/ecs/${PREFIX}/worker"

# ECS services: service name is identifier in the form "cluster/service"
tf_import "module.ecs.aws_ecs_service.api" "${PREFIX}-cluster/${PREFIX}-api"
tf_import "module.ecs.aws_ecs_service.worker" "${PREFIX}-cluster/${PREFIX}-worker"

# Task definitions — import the latest active revision by family
import_latest_task_def() {
    local addr="$1"
    local family="$2"
    local arn
    arn=$(aws ecs describe-task-definition --region "${REGION}" \
        --task-definition "${family}" \
        --query 'taskDefinition.taskDefinitionArn' --output text 2>/dev/null || echo "")
    tf_import "${addr}" "${arn}"
}
import_latest_task_def "module.ecs.aws_ecs_task_definition.api" "${PREFIX}-api"
import_latest_task_def "module.ecs.aws_ecs_task_definition.worker" "${PREFIX}-worker"

# Autoscaling targets and policies
tf_import "module.ecs.aws_appautoscaling_target.api" \
    "service/${PREFIX}-cluster/${PREFIX}-api/ecs/service/DesiredCount"
tf_import "module.ecs.aws_appautoscaling_target.worker" \
    "service/${PREFIX}-cluster/${PREFIX}-worker/ecs/service/DesiredCount"
tf_import "module.ecs.aws_appautoscaling_policy.api_cpu" \
    "ecs/service/${PREFIX}-cluster/${PREFIX}-api/DesiredCount/${PREFIX}-api-cpu"
tf_import "module.ecs.aws_appautoscaling_policy.worker_cpu" \
    "ecs/service/${PREFIX}-cluster/${PREFIX}-worker/DesiredCount/${PREFIX}-worker-cpu"

# ── Lambda module (disabled, skip log group only) ─────────────────────────
echo ""
echo "── Lambda (disabled, importing log group only) ──"
tf_import "module.lambda.aws_cloudwatch_log_group.s7_video_gen" "/aws/lambda/${PREFIX}-s7-video-gen"

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "============================================="
echo "Import complete. Running plan to verify..."
echo ""
terraform plan -var-file="${VAR_FILE}" -detailed-exitcode -input=false -no-color | tail -30 || true
echo ""
echo "If plan shows 'No changes', imports succeeded."
echo "If plan shows resources to CREATE, those imports failed — check logs above."
echo "If plan shows resources to UPDATE, minor drift — safe to apply."
