# stackr on AWS: the root an operator applies

`envs/prod` deploys stackr's AWS recipe ([RFC-0004](../../../../../../docs/stackr/rfcs/0004-hosting-recipes.md)) through the `stack` module ([ADR-0034](../../../../../../docs/stackr/adr/0034-the-stack-on-aws.md)). CI never applies it: tier 1 validates it, and plans it against a mocked AWS with `prod.tfvars.example`.

Not yet usable end to end: stackr's thin images aren't published until its release.

## What you need

- OpenTofu, from lattice's `.prototools`, and AWS CLI v2, which runs the one-off tasks (db-init, auth-keys, db-roles) and, for SSM port forwarding, its Session Manager plugin.
- An AWS account, and credentials for it: your shell's, or an AWS CLI profile, which `profile` names. To act as a role, name a profile with `role_arn`. The provider refuses any account but `account_id`.
- A public Route 53 hosted zone for the domain, already delegated to Route 53: the certificate is validated through it, and its validation waits until it resolves.
- The application's image, pullable without credentials: no private registry is wired.

## Once per account: the state bucket

The state is in S3, with S3's own lock file (`use_lockfile`): one bucket per account, and one key per deployment. Make the bucket once, by hand: versioned, encrypted, private, TLS only, and tidied.

```sh
export AWS_REGION=<region>
account=$(aws sts get-caller-identity --query Account --output text)
bucket=$account-stackr-state

# In us-east-1:
aws s3api create-bucket --bucket "$bucket"
# In any other region:
aws s3api create-bucket --bucket "$bucket" --create-bucket-configuration "LocationConstraint=$AWS_REGION"

aws s3api put-bucket-versioning --bucket "$bucket" --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket "$bucket" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-public-access-block --bucket "$bucket" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-policy --bucket "$bucket" --policy "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{
    \"Sid\": \"TLSOnly\", \"Effect\": \"Deny\", \"Principal\": \"*\", \"Action\": \"s3:*\",
    \"Resource\": [\"arn:aws:s3:::$bucket\", \"arn:aws:s3:::$bucket/*\"],
    \"Condition\": {\"Bool\": {\"aws:SecureTransport\": \"false\"}}
  }]
}"
aws s3api put-bucket-lifecycle-configuration --bucket "$bucket" --lifecycle-configuration '{
  "Rules": [{
    "ID": "tidy", "Status": "Enabled", "Filter": {},
    "NoncurrentVersionExpiration": {"NoncurrentDays": 90},
    "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7}
  }]
}'
```

S3's own keys (SSE-S3) encrypt it. SSE-KMS, with a key of your own, is the stricter choice: give `put-bucket-encryption` `"SSEAlgorithm":"aws:kms"` and the key, and whoever applies needs `kms:Encrypt`, `kms:Decrypt` and `kms:GenerateDataKey` on it.

Whoever applies a deployment needs, on the bucket, only its own key and that key's lock file:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": "s3:ListBucket", "Resource": "arn:aws:s3:::<bucket>",
      "Condition": { "StringLike": { "s3:prefix": ["<deployment>/*"] } } },
    { "Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::<bucket>/<deployment>/terraform.tfstate" },
    { "Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::<bucket>/<deployment>/terraform.tfstate.tflock" }
  ]
}
```

## A deployment

A deployment's `name` must be unique in the account: it names its resources, and its state's key, `<name>/terraform.tfstate`.

1. Copy `prod.tfvars.example` to `<deployment>.tfvars` and `prod.s3.tfbackend.example` to `<deployment>.s3.tfbackend`, and fill them in. The repository ignores both, and neither holds a secret.
2. Initialize with the deployment's state. `-reconfigure` switches between deployments in one checkout:

   ```sh
   tofu init -reconfigure -backend-config=<deployment>.s3.tfbackend
   ```

3. Plan, read the plan, and apply it:

   ```sh
   tofu plan -var-file=<deployment>.tfvars -out=<deployment>.tfplan
   tofu apply <deployment>.tfplan
   ```

4. Write the secrets that the `secrets_written_elsewhere` output lists, from files so they stay out of your shell's history. OpenTofu can't see them change, so deploy their reader again after writing one:

   ```sh
   cluster=$(tofu output -raw cluster_arn)
   aws secretsmanager put-secret-value --secret-id <name>/litellm-anthropic-api-key \
     --secret-string file://anthropic-api-key.txt
   aws ecs update-service --cluster "$cluster" --service litellm --force-new-deployment
   # GoTrue's SMTP password, if it has SMTP:
   aws secretsmanager put-secret-value --secret-id <name>/auth-smtp-password --secret-string file://smtp-password.txt
   aws ecs update-service --cluster "$cluster" --service gotrue --force-new-deployment
   ```

   LiteLLM starts once each provider's key has a value, and GoTrue once its SMTP password does.

## Rotating GoTrue's keys

auth-keys keeps a key set once it is written, since a new one ends every session signed with the old. To rotate it, remove it, and run auth-keys again: it writes a new key set, finds the service role's key no longer verifies, and writes that again too. GoTrue and the application then deploy again, and everyone signs in anew.

```sh
aws secretsmanager delete-secret --secret-id <name>/auth-jwt-keys --force-delete-without-recovery
tofu apply -var-file=<deployment>.tfvars -replace=module.stack.terraform_data.auth_keys
```

The apply makes the secret again, with no value, for auth-keys to write. To bring a key set of your own instead, write it, and run auth-keys again the same way, which keeps it:

```sh
aws secretsmanager put-secret-value --secret-id <name>/auth-jwt-keys --secret-string file://jwt-keys.json
tofu apply -var-file=<deployment>.tfvars -replace=module.stack.terraform_data.auth_keys
```

## The admin UIs

Operators reach Grafana, Langfuse and LiteLLM's admin UI with SSM port forwarding through the state host, which opens no port: AWS CLI v2 with the Session Manager plugin.

```sh
aws ssm start-session --target "$(tofu output -raw state_host_instance_id)" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters 'host=["grafana.stackr.internal"],portNumber=["3000"],localPortNumber=["3000"]'
```

Then open <http://localhost:3000>. Langfuse is `langfuse-web.stackr.internal` on 3000, and LiteLLM `litellm.stackr.internal` on 4000.

## What `envs/prod` fixes

It sets what an operator chooses above, and leaves the rest at the `stack` module's defaults: the environment `production`; RDS's, ElastiCache's and the services' sizes; the state host's `t4g.large`; 14 days of container logs; and every guard a destroy meets on (`destroyable = false`). Langfuse's first user is `admin@<domain>` unless `langfuse_admin_email` names another.

## Retiring a deployment

`tofu destroy` stops at the guards: RDS's and the ALB's deletion protection, the buckets that aren't empty, and the state host's volume, which it snapshots first. To retire one on purpose:

1. Take what you keep: RDS's final snapshot comes with the destroy, and the volume's too; copy anything else from the buckets.
2. Turn RDS's and the ALB's deletion protection off in the console or the CLI, and empty the buckets.
3. `tofu destroy -var-file=<deployment>.tfvars`.

The deleted secrets stay restorable for 30 days, and their names stay taken in the account until then: a new deployment with the same name must wait, or restore them, or force their deletion (`aws secretsmanager delete-secret --force-delete-without-recovery`).
