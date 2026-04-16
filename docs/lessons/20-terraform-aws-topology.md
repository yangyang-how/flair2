# 20. Terraform and the AWS Topology

> Infrastructure-as-code means the infrastructure IS documentation. This article reads the Terraform modules to explain the AWS topology — VPC, subnets, security groups, IAM roles — and teaches you how to read infra code as architecture.

## What Terraform is

Terraform is a tool that turns declarative configuration files into real cloud resources. You describe what you want ("I want a VPC with two public subnets and two private subnets"), and Terraform figures out the API calls to make it happen.

**The key property:** Terraform is **declarative**, not imperative. You don't write "create a VPC, then create a subnet, then attach an internet gateway." You write "there should be a VPC, there should be subnets, there should be an internet gateway." Terraform resolves dependencies and executes in the right order.

**State file:** Terraform tracks what it has created in a state file (`terraform.tfstate`). On subsequent runs, it compares the desired state (your `.tf` files) with the actual state (the state file) and makes only the necessary changes. Flair2 stores its state in S3 (`flair2-terraform-state-314727362981`).

## The module structure

```
terraform/
├── main.tf           # Root: VPC, subnets, gateways, NAT
├── variables.tf      # Input variables (region, CIDRs, project name)
├── outputs.tf        # Output values (ALB URL, etc.)
└── modules/
    ├── alb/          # Application Load Balancer
    ├── dynamodb/     # DynamoDB tables (dormant)
    ├── ecr/          # Elastic Container Registry
    ├── ecs/          # ECS Fargate (API + Worker services)
    ├── elasticache/  # Redis
    ├── frontend/     # S3 static website
    ├── iam/          # IAM roles and policies
    ├── lambda/       # Lambda function (dormant)
    └── s3/           # S3 data bucket (dormant)
```

**Module pattern:** each AWS service gets its own module with its own `main.tf`, `variables.tf`, and `outputs.tf`. The root `main.tf` calls each module and wires their outputs together (e.g., the ECS module needs the VPC ID from the root, the ALB target group ARN from the ALB module, etc.).

## The network layer: VPC, subnets, gateways

**File:** `terraform/main.tf`

### VPC

```hcl
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr        # e.g., "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
}
```

A VPC (Virtual Private Cloud) is an isolated network in AWS. Everything Flair2 runs inside this VPC. The CIDR block `10.0.0.0/16` gives you 65,536 IP addresses — plenty for a project this size.

### Subnets: public vs private

```hcl
resource "aws_subnet" "public" {
  count             = length(var.public_subnet_cidrs)   # 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.public_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]
  map_public_ip_on_launch = true
}

resource "aws_subnet" "private" {
  count             = length(var.private_subnet_cidrs)  # 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]
}
```

**Public subnets (2):** the ALB lives here. These subnets have a route to the internet gateway, so the ALB can receive internet traffic. `map_public_ip_on_launch = true` gives each resource a public IP.

**Private subnets (2):** ECS tasks and ElastiCache live here. No direct internet access. These resources communicate with the internet only through the NAT gateway (for outbound calls like LLM API requests).

**Two of each, across two availability zones:** AWS availability zones are physically separate data centers within a region. If one AZ goes down (fire, power outage), the other keeps running. Two subnets in two AZs is the minimum for high availability. The ALB distributes traffic across both.

### Internet Gateway and NAT Gateway

```hcl
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
}
```

**Internet Gateway:** allows inbound internet traffic to reach the ALB in public subnets.

**NAT Gateway:** allows outbound internet traffic from private subnets (ECS tasks calling Kimi API) without allowing inbound traffic. This is a one-way door: private resources can reach the internet, but the internet can't reach them directly.

**Why NAT costs money:** NAT gateways charge per hour and per GB of data processed. For a course project, this is the most expensive always-on resource. Production systems accept this cost for security; dev environments sometimes skip it and put everything in public subnets.

## Security groups: the firewall rules

Security groups are per-resource firewall rules. They specify what traffic is allowed in (ingress) and out (egress).

**ALB security group:** allows inbound HTTP (80) and HTTPS (443) from the internet. This is the only security group with public internet ingress.

**ECS security group:** allows inbound traffic only from the ALB security group. ECS tasks can't be reached directly from the internet — only through the ALB.

**ElastiCache security group:** allows inbound traffic only from the ECS security group. Redis can't be reached from the internet or even from the ALB — only from ECS tasks.

```
Internet → ALB (public subnets, ports 80/443)
              ↓ (ALB SG → ECS SG)
           ECS tasks (private subnets, port 8000)
              ↓ (ECS SG → ElastiCache SG)
           ElastiCache (private subnets, port 6379)
```

**The principle:** each layer can only be reached by the layer above it. This is defense in depth — even if an attacker compromises the ALB, they can't directly access Redis because the security group blocks it.

## IAM: who can do what

**File:** `terraform/modules/iam/main.tf`

IAM (Identity and Access Management) defines permissions. Flair2 has several roles:

**ECS Task Execution Role:** allows ECS to pull Docker images from ECR and read secrets from Secrets Manager. This role is used by the ECS agent (AWS infrastructure), not by the application code.

**ECS Task Role:** allows the application code running inside ECS tasks to access AWS services. This includes:
- `ssmmessages` permissions for ECS Exec (live debugging — PR #129/#130)
- Secrets Manager read access for API keys
- (Potentially) S3 and DynamoDB access if those services were active

**The distinction matters:** the execution role is for ECS infrastructure (pulling images, starting containers). The task role is for application code (reading secrets, calling AWS APIs). Separating them follows the principle of least privilege — the infrastructure doesn't need application permissions, and the application doesn't need infrastructure permissions.

**PR #119 note:** the project originally used `LabRole` (a school-provided catch-all IAM role). PR #119 replaced it with purpose-built roles for the personal AWS account. This is a common migration: start with broad permissions for development, then narrow them for production.

## How the modules connect

The root `main.tf` wires modules together by passing outputs as inputs:

```
VPC (root main.tf)
 ├── outputs: vpc_id, public_subnet_ids, private_subnet_ids
 │
 ├── ALB module
 │    inputs: vpc_id, public_subnet_ids
 │    outputs: target_group_arn, alb_dns_name
 │
 ├── ECS module
 │    inputs: vpc_id, private_subnet_ids, target_group_arn, ecr_repo_url
 │    outputs: api_service_name, worker_service_name
 │
 ├── ElastiCache module
 │    inputs: vpc_id, private_subnet_ids
 │    outputs: redis_endpoint
 │
 ├── ECR module
 │    inputs: project name
 │    outputs: repository_url
 │
 └── IAM module
      inputs: project name
      outputs: task_role_arn, execution_role_arn
```

**The dependency graph is explicit.** You can read `main.tf` and understand the deployment order: VPC first, then subnets, then everything else in parallel. Terraform resolves this automatically from the input/output references.

## Reading Terraform as architecture documentation

Here's the skill: **Terraform files describe the real deployed infrastructure, not a wish.** Unlike architecture diagrams (which may be outdated), Terraform is executable — if it doesn't match reality, `terraform plan` shows the drift.

When you encounter a new project with Terraform:

1. **Start with `main.tf`** — understand the network topology (VPC, subnets, gateways)
2. **Read the module list** — each module is a deployed component
3. **Check `variables.tf`** — environment-specific values (region, instance sizes, CIDR ranges)
4. **Check `outputs.tf`** — what the deployment exposes (ALB URL, Redis endpoint)
5. **Look for dormant modules** — things provisioned but not wired into the application (DynamoDB, S3, Lambda in Flair2's case)

**The dormant modules tell a story.** They represent planned features that were scoped out, or infrastructure provisioned "just in case." In Flair2, DynamoDB and S3 are the future persistence layer that was never needed because Redis with 24-hour TTLs was sufficient.

## What you should take from this

1. **Terraform IS the architecture diagram.** It's executable, version-controlled, and always matches reality (or shows you where it doesn't).

2. **Public vs private subnets is the first security decision.** Put load balancers in public subnets, everything else in private. This is the baseline.

3. **Security groups are layered firewalls.** Each component only accepts traffic from the component above it. Internet → ALB → ECS → Redis, each transition controlled by a security group rule.

4. **IAM roles follow least privilege.** Execution role for infrastructure, task role for application. Don't use one broad role for everything.

5. **Module structure mirrors component boundaries.** One module per AWS service, with explicit inputs and outputs. This makes the dependency graph readable.

---

***Next: [ECS Fargate: Two Services, One Cluster](21-ecs-fargate.md) — why API and Worker scale independently, and why CPU was the wrong metric for Workers.***
