project = "flair2"
env     = "dev"

aws_region = "us-west-2"

vpc_cidr             = "10.0.0.0/16"
public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.11.0/24", "10.0.12.0/24"]
availability_zones   = ["us-west-2a", "us-west-2b"]

# Create secrets manually before apply:
#   aws secretsmanager create-secret --name flair2/dev/kimi-api-key --secret-string "YOUR_KEY"
#   aws secretsmanager create-secret --name flair2/dev/gemini-api-key --secret-string "YOUR_KEY"
# Then paste the ARNs returned by the above commands here.
kimi_api_key_secret_arn   = "REPLACE_WITH_ARN_AFTER_CREATING_SECRET"
gemini_api_key_secret_arn = "REPLACE_WITH_ARN_AFTER_CREATING_SECRET"
