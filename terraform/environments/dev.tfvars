project = "flair2"
env     = "dev"

aws_region = "us-west-2"

vpc_cidr             = "10.0.0.0/16"
public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.11.0/24", "10.0.12.0/24"]
availability_zones   = ["us-west-2a", "us-west-2b"]

# Create the Kimi API key secret manually before apply:
#   aws secretsmanager create-secret --name flair2/dev/kimi-api-key --secret-string "YOUR_KEY"
# Then paste the ARN returned by the command here.
kimi_api_key_secret_arn = "arn:aws:secretsmanager:us-west-2:966294739208:secret:flair2/dev/kimi-api-key-JYvv9k"
