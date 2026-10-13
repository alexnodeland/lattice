# stackr on AWS: the root an operator applies

`envs/prod` deploys stackr's AWS recipe ([RFC-0004](../../../../../../docs/stackr/rfcs/0004-hosting-recipes.md)) through the `stack` module ([ADR-0034](../../../../../../docs/stackr/adr/0034-the-stack-on-aws.md)). CI never applies it: tier 1 only validates it.

## Once per account: the state bucket

Its state is in S3, with S3's own lock file (`use_lockfile`): one bucket per account, and one key per deployment. Make the bucket once, by hand, versioned, encrypted, and private:

```sh
bucket=<account>-stackr-state
aws s3api create-bucket --bucket "$bucket" --region <region> \
  --create-bucket-configuration LocationConstraint=<region>   # leave this out in us-east-1
aws s3api put-bucket-versioning --bucket "$bucket" --versioning-configuration Status=Enabled
aws s3api put-bucket-encryption --bucket "$bucket" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-public-access-block --bucket "$bucket" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

## A deployment

You need OpenTofu (lattice's `.prototools`), AWS CLI v2, and credentials for the account. OpenTofu runs the one-off tasks (db-init, auth-keys, db-roles) with the AWS CLI, in your shell's environment: if the provider's credentials come from anywhere else, such as a profile you don't export, give them in `run_task_environment` (`{ AWS_PROFILE = "<profile>" }`).

1. Copy `prod.tfvars.example` to `<deployment>.tfvars`, and fill it in. The repository ignores `*.tfvars`, and the file holds no secret.
2. Initialize with the deployment's key:

   ```sh
   tofu init -backend-config="bucket=$bucket" -backend-config="key=<deployment>/terraform.tfstate" \
     -backend-config="region=<region>"
   ```

3. Plan and apply:

   ```sh
   tofu apply -var-file=<deployment>.tfvars
   ```

4. Write the secrets that `secrets_written_elsewhere` lists, such as the providers' API keys. OpenTofu can't see them change, so deploy their reader again after writing one:

   ```sh
   aws ecs update-service --cluster <name> --service litellm --force-new-deployment
   ```

   LiteLLM starts once each provider's key has a value, and GoTrue once its SMTP password does, if it has SMTP.

Operators reach Grafana, Langfuse and LiteLLM's admin UI with SSM port forwarding through `state_host_instance_id`.
