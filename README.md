# AWS Sweep by Tag

A script for deleting AWS resources by tag key and value.

## Usage

Eventually, there are plans to turn this into a CLI tool, but while it is still in development you'll have to clone the repo to use.

To start the script, run:

```shell
python main.py
```

You script will use your default AWS credentials, but you can optionally export an AWS profile, access key and secret access key combination, or session token to use as credentials.

```shell
export AWS_PROFILE=<profile_name>
python main.py

# or
export AWS_ACCESS_KEY_ID=<access_key_id>
export AWS_SECRET_ACCESS_KEY=<secret_access_key>
export AWS_SESSION_TOKEN=<session_token>
python main.py
```

When the script starts you will be prompted for:

- Tag key
- Tag value
- Regions to search (separate multiple regions with commas)

If resources are found that match the tag key/value provided a list of resources will be returned and you will be prompted if you really want to delete them. If you select "y", the next prompt will ask if you want to be prompted before each resource is deleted; useful for when you don't want to delete all matching resources. The first prompt is a little unclear about this and will be clarified eventually.

### Other Prompts

You may be prompted for various reasons during the deletion process. For example, if you are deleting a DynamoDB table or S3 bucket the script checks to make sure they are empty before deleting, and provides a warning along with a prompt asking if you really want to delete all objects/items before deleting the resource.

## Supported Resources

This script is not meant to be comprehensive in terms of supporting all AWS resource types. The intention is to support core services, along with a few commonly used non-core services.

Furthermore, it is intended for more macro-level deletion. So, for example, it doesn't delete a CloudFront origin, but it can delete an entire CloudFront distribution.

### Currently Supported Resources

The plan is to gradually add more supported resources, but these are the resources that are currently supported:

- API Gatway: Should work for all types but websocket APIs have not been tested
- Autoscaling Tables
- CloudFront Distributions
- DynamoDB Tables
- AMIs and associated Snapshots
- EC2 Instances
- EIPs
- Internet Gateways
- NAT Gateways
- Route Tables
- Subnets
- VPC Endpoints
- VPCs
- Elastic Load Balancers (all types but classic) and associated listeners/target groups
- Lambda Functions
- S3 buckets
- SNS Topics
- SQS Queues
