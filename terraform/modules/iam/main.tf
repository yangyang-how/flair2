# Learner Lab does not allow creating IAM roles or policies.
# The lab pre-provisions a single "LabRole" with broad permissions.
# We reference it here so other modules can use it for ECS and Lambda.

data "aws_iam_role" "lab_role" {
  name = "LabRole"
}
