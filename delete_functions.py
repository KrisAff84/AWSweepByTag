"""
Deletion functions for individual resource types

Functions are ordered based on service and then resource.

Functions By Service:
    APIGW:
        - delete_api:
        - delete_rest_api

    Application Auto Scaling:
        - delete_application_autoscaling

    Autoscaling:
        - delete_autoscaling_group

    CloudFront:
        - delete_cloudfront_distribution
        - disable_cloudfront_distribution
        - wait_for_distribution_disabled

    DynamoDB:
        - delete_dynamodb_table

    EC2:
        - deregister_ami
        - delete_ec2_instance
        - ec2_waiter
        - release_eip
        - delete_internet_gateway
        - delete_nat_gateway
        - delete_route_table
        - delete_snapshot
        - delete_subnet
        - delete_vpc_endpoint
        - delete_vpc

    Elastic Load Balancing:
        - delete_elastic_load_balancer
        - delete_listener
        - delete_target_group

    Lambda:
        - delete_lambda_function

    S3:
        - delete_s3_bucket

    SNS:
        - delete_sns_topic

    SQS:
        - delete_sqs_queue
"""

import time
from datetime import datetime
import json
import botocore.exceptions
import boto3
import text_formatting as tf


######################### API GW Services ###########################

# This has been tested and works. The same logic needs to be updated for the REST API function.
def delete_api(arn: str, region: str) -> list[dict] | None:
    """
    Delete HTTP or websocket API from API GW in a given region.

    1. Checks API for any associated VPC links
    2. Attempts to delete API
    3. Prints success or failure message depending on response, along with the response itself
    4. Prompts user to delete any associated VPC links if present
    5. Attempts to delete each VPC link while printing success or failure message along with each response
    6. Waits for all VPC links to become inactive or non-existent before exiting function as long as retries aren't exceeded
    7. Prints error message if VPC links are still active after retries are exceeded

    Args:
        arn (str): The ARN of the API to delete
        region (str): The AWS region where the API is located
    """

    client = boto3.client('apigatewayv2', region_name=region)
    api_id = arn.split('/')[-1]
    tf.header_print(f"Deleting API {api_id} in {region}...")

    # Gather any integrations using VPC_LINK
    integrations = client.get_integrations(ApiId=api_id)
    vpc_link_ids = []

    for integration in integrations.get('Items', []):
        if integration.get('ConnectionType') == 'VPC_LINK':
            conn_id = integration.get('ConnectionId')
            if conn_id:
                vpc_link_ids.append(conn_id)

    # Delete the API
    try:
        response = client.delete_api(ApiId=api_id)
        status_code = response['ResponseMetadata']['HTTPStatusCode']

        if 200 <= status_code < 300:
            tf.success_print(f"API '{arn}' was successfully deleted")
        else:
            tf.failure_print(f"API '{arn}' was not successfully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))

    except botocore.exceptions.ClientError:
        raise

    print()
    # Ask if user wants to delete associated VPC links if there are any
    delete_vpc_links = 'n'
    if vpc_link_ids:
        vpc_links_for_retry = []
        vpc_links_successful_delete = []
        delete_vpc_links = tf.y_n_prompt(f'Found {len(vpc_link_ids)} VPC link(s) associated with API {arn}. Delete them?')
        print()
        if delete_vpc_links != 'y':
            tf.indent_print("VPC links will not be deleted")
            return

        else:
            for vpc_link_id in vpc_link_ids:
                vpc_link = delete_vpc_link(vpc_link_id, region, True)
                if vpc_link:
                    vpc_links_for_retry.extend(vpc_link)
                else:
                    vpc_links_successful_delete.append(vpc_link_id)

            if vpc_links_successful_delete:
                vpc_link_waiter(vpc_links_successful_delete, region)

            if vpc_links_for_retry:
                return vpc_links_for_retry

    # Exit if no VPC links were found
    else:
        return


# TODO: This still needs to be tested with the VPC link logic, although the REST API has been confirmed to delete successfully
def delete_rest_api(arn: str, region: str) -> None:
    """
    Delete REST API from API GW in a given region.

    If VPC links exist and are deleted, the function waits for them to become fully deleted before proceeding.

    Args:
        arn (str): The ARN of the API to delete
        region (str): The AWS region where the API is located
    """

    client = boto3.client('apigateway', region_name=region)
    api_id = arn.split('/')[-1]
    tf.header_print(f"Deleting REST API {api_id} in {region}...")
    vpc_link_ids = set()

    # Checks for VPC Links in method integrations
    resources = client.get_resources(restApiId=api_id, limit=500)

    for resource in resources['items']:
        resource_id = resource['id']
        if 'resourceMethods' in resource:
            for http_method in resource['resourceMethods']:
                try:
                    method_resp = client.get_integration(
                        restApiId=api_id,
                        resourceId=resource_id,
                        httpMethod=http_method
                    )
                    if method_resp.get('connectionType') == 'VPC_LINK':
                        conn_id = method_resp.get('connectionId')
                        if conn_id:
                            vpc_link_ids.add(conn_id)
                except botocore.exceptions.ClientError as e:
                    tf.failure_print(f"Error retrieving integration for {http_method} on resource {resource_id}: {e}")

    # Prompts user to delete VPC links if they exist.
    if vpc_link_ids:
        delete_vpc_links = 'n'
        delete_vpc_links = tf.y_n_prompt(f"Found {len(vpc_link_ids)} VPC link(s) associated with REST API {arn}. Delete them?")
        if delete_vpc_links != 'y':
            tf.indent_print("VPC links will not be deleted.")
        else:
            # Deletes VPC links if user confirms
            for vpc_link_id in vpc_link_ids:
                try:
                    response = client.delete_vpc_link(VpcLinkId=vpc_link_id)
                    status_code = response['ResponseMetadata']['HTTPStatusCode']
                    if 200 <= status_code < 300:
                        tf.success_print(f"VPC link {vpc_link_id} was successfully deleted")
                    else:
                        tf.failure_print(f"VPC link {vpc_link_id} was not successfully deleted")
                    tf.response_print(json.dumps(response, indent=4, default=str))
                except botocore.exceptions.ClientError as e:
                    tf.failure_print(f"Error deleting VPC link {vpc_link_id}: {e}")

    # Deletes the REST API
    try:
        response = client.delete_rest_api(restApiId=api_id)
        status_code = response['ResponseMetadata']['HTTPStatusCode']
        if 200 <= status_code < 300:
            tf.success_print(f"REST API {arn} was successfully deleted")
        else:
            tf.failure_print(f"REST API {arn} was not successfully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))
    except botocore.exceptions.ClientError as e:
        tf.indent_print(f"Failed to delete API {arn}: {e}")

    # Wait for VPC links to be deleted or reach a non-active state
    if vpc_link_ids and delete_vpc_links == 'y':
        tf.indent_print("Checking status(es) of VPC link(s) to avoid dependency violations...\n")
        max_retries = 5
        retry_delay = 5
        retry = 0

        while retry <= max_retries:
            still_exists = []

            for vpc_link_id in vpc_link_ids:
                try:
                    response = client.get_vpc_link(vpcLinkId=vpc_link_id)
                    status = response.get('status', '')
                    tf.indent_print(f"VPC link {vpc_link_id} status: {status}")
                    still_exists.append((vpc_link_id, status))
                except botocore.exceptions.ClientError as e:
                    if e.response['Error']['Code'] == 'NotFoundException':
                        tf.success_print(f"VPC link {vpc_link_id} has been fully deleted.")
                        continue
                    else:
                        tf.failure_print(f"Error checking status for VPC link {vpc_link_id}: {e}")
                        still_exists.append((vpc_link_id, 'ERROR'))

            if not still_exists:
                tf.success_print("All VPC links have been fully deleted.")
                break
            else:
                tf.indent_print("Waiting for VPC links to be fully deleted...")
                retry += 1
                time.sleep(retry_delay)

        if retry >= max_retries:
            tf.failure_print("Some VPC links may still exist. Please check manually.")

    print()


def delete_vpc_link(vpc_link_id: str, region: str, apigw_function: bool=False) -> list[dict] | None:
    """
    Delete VPC Link in a given region by VPC Link ID.

    Can be called from either delete_api, delete_rest_api, or from the retry logic

    Args:
        vpc_link_id (str): The ID of the VPC Link to delete
        region (str): The region in which the VPC Link is located
        apigw_function (bool, optional): Whether the function was called by an API delete function. Defaults to False.
    """

    client = boto3.client('apigatewayv2', region_name=region)

    if not apigw_function:
        tf.header_print(f"Deleting VPC link {vpc_link_id} in {region}...")

    else:
        tf.subheader_print(f"Deleting VPC link {vpc_link_id} in {region}...")

    resource = {
        "resource_type": "vpclink",
        "arn": vpc_link_id,
        "service": "apigatewayv2",
        "region": region
    }

    # TODO: Implement logic to call vpc_link_waiter if called from retry logic
    # If called from API delete functions, waiter is called within those functions
    try:
        response = client.delete_vpc_link(VpcLinkId=vpc_link_id)
        status_code = response['ResponseMetadata']['HTTPStatusCode']

        if 200 <= status_code < 300:
            tf.success_print(f"VPC link {vpc_link_id} was successfully deleted")
            tf.response_print(json.dumps(response, indent=4, default=str))
            if not apigw_function:
                vpc_link_waiter([vpc_link_id], region)
                return
        else:
            tf.failure_print(f"VPC link {vpc_link_id} was not successfully deleted. Retrying later...")
            tf.response_print(json.dumps(response, indent=4, default=str))
            return resource

    except botocore.exceptions.ClientError:
        return [resource]


def vpc_link_waiter(vpc_link_ids: list, region: str) -> None:
    """
    Waits for VPC Links to become inactive or non-existent to avoid dependency issues
    """

    tf.indent_print("Checking status(es) of VPC link(s) to avoid dependency violations...\n")

    client = boto3.client('apigatewayv2', region_name=region)
    max_retries = 5
    retry_delay = 5
    retry = 0

    while retry <= max_retries:
        vpc_link_statuses = []
        all_inactive = True

        for vpc_link_id in vpc_link_ids:
            try:
                response = client.get_vpc_link(VpcLinkId=vpc_link_id)

                if 'VpcLink' in response:
                    status = response['VpcLink']['VpcLinkStatus']
                else:
                    status = response.get('VpcLinkStatus') or response.get('status')  # fallback
                vpc_link_statuses.append((vpc_link_id, status))
                if status in ('DELETING', 'PENDING', 'AVAILABLE'):
                    all_inactive = False

            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == 'NotFoundException':
                    tf.success_print(f"VPC link {vpc_link_id} is already deleted")
                else:
                    tf.indent_print(f"Error checking status for VPC link {vpc_link_id}: {e}")
                    all_inactive = False

        print()
        if all_inactive:
            tf.success_print("All VPC links are inactive or deleted")
            break
        else:
            tf.indent_print("Some VPC links are still active:")
            for vpc_link_id, status in vpc_link_statuses:
                tf.indent_print(f"  - {vpc_link_id}: {status}")
            tf.indent_print(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
            retry += 1

    if retry > max_retries:
        tf.failure_print("Some VPC links may still be active. Please check manually")
    print()

################# Application Autoscaling Service ###################

def delete_application_autoscaling(service_namespace: str, resource_id: str, region: str) -> None:
    """
    Find and delete all Application Autoscaling targets and policies for a given resource.

    Called from other delete functions when the resource could potentially have application autoscaling enabled.

    Args:
        service_namespace (str): The namespace of the AWS service.
        resource_id (str): The ID of the resource to delete policies for. Varies per resource. See boto3 docs for application autoscaling for more info.
        region (str): The region the resource is in.
    """

    tf.subheader_print(f"Checking for attached Application Autoscaling Policies and Targets for {resource_id}...")
    client = boto3.client('application-autoscaling', region_name=region)
    response = client.describe_scalable_targets(ServiceNamespace=service_namespace, ResourceIds=[resource_id])

    # tf.indent_print("Describe Scalable Targets Response:")
    # tf.response_print(json.dumps(response, indent=4, default=str))

    if not response['ScalableTargets']:
        tf.indent_print(f"No scalable targets found for {resource_id}.")
        return

    # Get scalable dimensions from response - needed for deregister_scalable_target and describe_scaling_policies
    scalable_dimensions = []
    for target in response['ScalableTargets']:
        scalable_dimensions.append(target['ScalableDimension'])

    # Get policy names for each scalable dimension
    policy_dimension_map = {}
    for dimension in scalable_dimensions:
        response = client.describe_scaling_policies(
            ServiceNamespace=service_namespace,
            ResourceId=resource_id,
            ScalableDimension=dimension
        )
        policy_names = [policy['PolicyName'] for policy in response.get('ScalingPolicies', [])]
        if policy_names:
            policy_dimension_map[dimension] = policy_names

    # Delete policies
    # TODO: Consider putting this into its own function and returning a resource for retry in event of failure
    tf.subheader_print(f"Deleting Application Autoscaling Policies and Targets for {resource_id}...")
    for dimension, policy_names in policy_dimension_map.items():
        for policy_name in policy_names:
            response = client.delete_scaling_policy(
                PolicyName=policy_name,
                ServiceNamespace=service_namespace,
                ResourceId=resource_id,
                ScalableDimension=dimension
            )
            if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
                tf.success_print(f"Successfully deleted scaling policy '{policy_name}' for {dimension}")
            else:
                tf.failure_print(f"Failed to delete scaling policy '{policy_name}' for {dimension}")
            tf.response_print(json.dumps(response, indent=4, default=str))

    # Delete scalable targets
    for dimension in scalable_dimensions:
        response = client.deregister_scalable_target(ServiceNamespace=service_namespace, ResourceId=resource_id, ScalableDimension=dimension)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.success_print(f"Successfully deregistered Application Auto Scaling target for {dimension}.")
        else:
            tf.failure_print(f"Failed to deregister Application Auto Scaling target for {dimension}.")
        tf.response_print(json.dumps(response, indent=4, default=str))

####################### AutoScaling Service #########################

def delete_autoscaling_group(arn: str, region: str) -> list[dict] | None:
    """
    Delete an autoscaling group and terminate all instances in the group

    1. Autoscaling group is checked for any instances
    2. Autoscaling group is deleted, function returns if not instances exist, any exceptions are raised
    3. If instances exist, they are terminated with delete_ec2_instance and ec2_waiter is called to wait for full termination
    4. If instances fail to delete, they are added to a list of instances to retry and returned

    The step to delete instances seems redundant, but this is done to speed up the process, as
    there is often a lag between deleting an autoscaling group and when instances are actually
    terminated.

    Args:
        arn (str): The ARN of the autoscaling group to delete
        region (str): The region the autoscaling group is in

    Returns:
        list[dict] | None - List of instances (as dicts) that failed to delete, or None if no instances exist or all were successfully terminated.
    """

    tf.header_print(f"Deleting autoscaling group {arn} in {region}...")
    client = boto3.client('autoscaling', region_name=region)
    asg_name = arn.split('/')[-1]
    account_id = arn.split(':')[4]

    instance_ids = [
        instance["InstanceId"]
        for instance in client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])["AutoScalingGroups"][0]["Instances"]
    ]

    instance_arns = [
        f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}"
        for instance_id in instance_ids
    ]
    try:
        response = client.delete_auto_scaling_group(AutoScalingGroupName=asg_name, ForceDelete=True)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.success_print(f"Autoscaling group {arn} deletion initiated successfully")
        else:
            tf.failure_print(f"Autoscaling group {arn} was not successfully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))

    except botocore.exceptions.ClientError:
        raise

    if not instance_arns:
        return

    # Terminate any instances if they exist and wait until they are fully terminated
    instances_to_retry = []

    for instance in instance_arns:
        try:
            delete_ec2_instance(instance, region, True)

        except Exception as e:
            tf.failure_print(f"Error deleting instances in autoscaling group '{asg_name}':")
            tf.indent_print(e, 6)
            instance_map = {
                "arn": instance,
                "service": "ec2",
                "resource_type": "instance",
                "region": region
            }
            instances_to_retry.append(instance_map)

    if not instances_to_retry:
        instance_ids_to_confirm = instance_ids

    else:
        instance_ids_to_confirm = [
            arn.split('/')[-1]
            for arn in instance_arns
            if arn not in [instance['arn'] for instance in instances_to_retry]
        ]

    tf.indent_print("Waiting for autoscaling instances to shut down to avoid dependency violations...")
    ec2_waiter(instance_ids_to_confirm, region)
    tf.success_print("All instances in autoscaling group are terminated.")
    print()

    return instances_to_retry

####################### CloudFront Service ##########################

def delete_cloudfront_distribution(arn: str) -> None:
    """
    Delete a CloudFront distribution

    If the distribution is not yet fully disabled, it will be retried by the retry_failed_deletions
    function. Retries should not be needed however, because the function that calls this first calls the
    wait_for_distribution_disabled function. Before attempting to delete a get_distribution request is
    made first to retrieve the latest ETag, which is required for the delete_distribution request.

    Args:
        arn (str): The ARN of the CloudFront distribution to delete
    """

    client = boto3.client('cloudfront')
    distribution_id = arn.split('/')[-1]
    tf.header_print(f"Deleting CloudFront distribution {distribution_id}...")

    # Get the new ETag after disable
    distribution = client.get_distribution(Id=distribution_id)
    etag = distribution['ETag']

    # Now delete the distribution
    try:
        response = client.delete_distribution(
            Id=distribution_id,
            IfMatch=etag
        )
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.success_print(f"CloudFront distribution {arn} was successfully deleted")
        else:
            tf.failure_print(f"CloudFront distribution {arn} was not successfully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))

    except Exception as e:
        tf.failure_print(f"Delete error (CloudFront {distribution_id}): {str(e)}\n")
        raise


def disable_cloudfront_distribution(arn: str) -> bool:
    """
    Disable a CloudFront distribution

    If distribution is already disabled it will attempt to delete.
    If deletion is unsuccessful, or if the distribution is not already disabled
    it will return retry = True to be tried later, upon which wait_for_distribution_disabled
    will be called before delete_cloudfront_distribution is called again.

    Args:
        arn (str): The ARN of the CloudFront distribution to disable

    Returns:
        bool - True if the distribution needs to be retried for deletion
    """

    client = boto3.client('cloudfront')
    distribution_id = arn.split('/')[-1]
    tf.header_print(f"Disabling CloudFront distribution {distribution_id}...")
     # Get the current distribution config
    distribution = client.get_distribution(Id=distribution_id)
    etag = distribution['ETag']

    # Check if distribution is already disabled
    if distribution['Distribution']['Status'] == 'Deployed' and distribution['Distribution']['DistributionConfig']['Enabled']:
        # Get the current config
        config = distribution['Distribution']['DistributionConfig']

        # Set enabled to False
        config['Enabled'] = False

        # Update the distribution to disable it
        tf.indent_print(f"Disabling CloudFront distribution {distribution_id}. Will come back to delete...")
        client.update_distribution(
            Id=distribution_id,
            DistributionConfig=config,
            IfMatch=etag
        )
        retry = True

    else:
        tf.indent_print(f"CloudFront distribution {distribution_id} is already disabled. Trying to delete...")
        try:
            response = client.delete_distribution(
                Id=distribution_id,
                IfMatch=etag
            )
            if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
                tf.success_print(f"CloudFront distribution {arn} was successfully deleted")
                retry = False
            else:
                tf.failure_print(f"CloudFront distribution {arn} was not successfully deleted")
            tf.response_print(json.dumps(response, indent=4, default=str))
        except client.exceptions.DistributionNotDisabled:
            tf.indent_print(f"CloudFront distribution {distribution_id} is not yet fully disabled. Will retry later...\n")
            retry = True
        except Exception as e:
            tf.indent_print(f"Error deleting CloudFront distribution {distribution_id}: {str(e)}\n")
            retry = True

    return retry


def wait_for_distribution_disabled(arn: str) -> None:
    """
    Wait for a CloudFront distribution to be fully disabled

    Args:
        arn (str): The arn of the CloudFront distribution to wait for
    """

    client = boto3.client('cloudfront')
    distribution_id = arn.split('/')[-1]
    tf.header_print(f"Waiting for CloudFront distribution {distribution_id} to be disabled...")
    waiter = client.get_waiter('distribution_deployed')
    waiter.wait(
        Id=distribution_id,
        WaiterConfig={
            'Delay': 30,
            'MaxAttempts': 20
        }
    )
    tf.success_print(f"CloudFront distribution {distribution_id} disabled.")
    print()

######################## DynamoDB Service ###########################

def create_dynamodb_table_backup(arn: str, region: str) -> bool:
    """
    Create a backup of a DynamoDB table

    Called by delete_dynamodb_function if table is not empty.

    1. Prompts user if they would like to create backup - if not, returns False
    2. Prompts user for a name for the backup or accepts default
    3. Attempts to create backup with a max of 5 retries, with exponential backoff (starting at 1 second)
    4. If backup is created successfully, returns False. If not, returns True to prompt user for deletion

    Args:
        arn (str): The ARN of the DynamoDB table to backup
        region (str): The region the DynamoDB table is in

    Returns:
        bool: True if user needs to be prompted for deletion (if backup creation fails)
    """

    table_name = arn.split('/')[-1]
    client = boto3.client('dynamodb', region_name=region)

    backup = tf.y_n_prompt(f"Would you like to create a backup before deleting table '{table_name}'?")
    print()

    if backup != "y":
        tf.indent_print("Skipping backup creation...")
        return False

    else:
        # Prompt users to enter a name for the backup or accept default (<table_name>-<timestamp in YYYYMMDD-HHMMSS format>)
        # If a name is provided, it will be prefixed to table name but still append timestamp (<table_name>-<user_name>-<timestamp>)
        tf.indent_print("Optional: Enter a suffix for the backup name or press Enter to accept the default")
        tf.indent_print("Default: {table_name}-{timestamp} | With suffix: {table_name}-{user_suffix}-{timestamp}")
        table_suffix = tf.custom_prompt("Optional suffix: ")
        print()
        tf.subheader_print(f"Creating backup for DynamoDB table '{table_name}'...")
        table_suffix = f"{table_suffix}-" if table_suffix else ""
        backup_prefix = f"{table_name}-{table_suffix}"
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_name = f"{backup_prefix}{timestamp}"

        max_retries = 5
        retry_delay = 1
        retry_number = 0

        while retry_number < max_retries:
            try:
                response = client.create_backup(
                    TableName=table_name,
                    BackupName=backup_name
                )

                if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
                    tf.success_print("Backup created successfully:")
                    tf.response_print(json.dumps(response, indent=4, default=str))
                    return False
                else:
                    tf.failure_print("Backup creation failed:")
                    tf.response_print(json.dumps(response, indent=4, default=str))
                    retry_number += 1
                    time.sleep(retry_delay)
                    retry_delay += 1

            except botocore.exceptions.ClientError as e:
                error_code = e.response['Error']['Code']

                if error_code == 'TableNotFoundException':
                    tf.indent_print(f"Could not create backup because of error '{error_code}'.")
                    return False

                else:
                    tf.failure_print(f"Error backing up DynamoDB table {table_name}: {e}\n")
                    tf.indent_print("Trying again...")
                    retry_number += 1
                    time.sleep(retry_delay)
                    retry_delay += 1

        tf.failure_print("Max retries reached. Skipping backup creation...")
        return True


def delete_dynamodb_table(arn: str, region: str) -> list[dict] | None:
    """
    Delete a DynamoDB table.

    If the table has deletion protection or items, the user will be prompted before proceeding.
    1. Table is checked for billing mode and deletion protection
    2. If deletion protection is enabled, user is warned and prompted to disable it
    3. Deletion protection is disabled if user confirms
    4. Table is checked for items by a scan with a limit of 1
    5. If items are found, user is warned and prompted to delete them and the table
    6. If user confirms, create_dynamodb_table_backup is called to prompt user to create backup
    7. If billing mode is PROVISIONED, application autoscaling policies and targets are checked for and deleted
    8. Table is deleted - if failure response table is returned for retry.

    Args:
        arn (str): The ARN of the DynamoDB table to delete
        region (str): The region the DynamoDB table is in

    Returns:
        list[dict] - Table that is marked for retry in case of failure, or None if no retries are needed

    Raises:
        botocore.exceptions.ClientError - Retries handled in delete_resource function.
    """

    tf.header_print(f"Deleting DynamoDB table '{arn}' in {region}...")
    client = boto3.client('dynamodb', region_name=region)
    table_name = arn.split('/')[-1]
    service_namespace = 'dynamodb'
    table_resource_id = f'table/{table_name}'

    # Check for deletion protection
    try:
        table_info = client.describe_table(TableName=table_name)['Table']
        billing_mode = table_info.get('BillingModeSummary', {}).get('BillingMode', 'Unknown')

    except client.exceptions.ResourceNotFoundException:
        tf.indent_print(f"Table '{table_name}' does not exist. It's possible that it has been deleted already.")
        return

    deletion_protection = table_info.get('DeletionProtectionEnabled', False)
    if deletion_protection:
        disable_protection = tf.warning_confirmation(f"Table '{table_name}' has deletion protection enabled. Disable it?")
        if disable_protection != 'yes':
            tf.indent_print(f"Skipping deletion of DynamoDB table '{table_name}'")
            return

        # Disable deletion protection
        response = client.update_table(
            TableName=table_name,
            DeletionProtectionEnabled=False
        )
        tf.success_print(f"Deletion protection disabled for table '{table_name}'")
        tf.response_print(json.dumps(response, indent=4, default=str))

    # Check if table has items
    response = client.scan(TableName=table_name, Limit=1)
    if len(response.get('Items', [])) > 0:
        confirm = tf.warning_confirmation(f"Table '{table_name}' is not empty. Delete all items and the table?")
        print()
        if confirm != 'yes':
            tf.indent_print(f"Skipping deletion of DynamoDB table '{table_name}'")
            return

        # Prompt and create backup if table is not empty

        prompt_for_deletion = create_dynamodb_table_backup(arn, region)

        if prompt_for_deletion:
            delete = tf.warning_confirmation(f"Backup of table '{table_name}' could not be created. Do you still want to delete the table?")

            if delete != 'yes':
                tf.indent_print(f"Skipping deletion of DynamoDB table '{table_name}'...")
                return


    # Delete the table
    tf.subheader_print(f"Proceeding with deletion of DynamoDB table '{table_name}'")
    print()
    try:
        response = client.delete_table(TableName=table_name)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.success_print(f"Table '{table_name}' was successfully deleted")
        else:
            tf.failure_print(f"Table '{table_name}' was not successfully deleted")
            return [{
                "resource_type": "table",
                "service": "dynamodb",
                "arn": arn,
                "region": region
            }]
        tf.response_print(json.dumps(response, indent=4, default=str))

        if billing_mode == 'PAY_PER_REQUEST':
            return

        # Delete Application AutoScaling Policies and Targets for the table and its GSI(s) if they exist
        global_secondary_index_names = [gsi["IndexName"] for gsi in table_info.get("GlobalSecondaryIndexes", [])]
        delete_application_autoscaling(service_namespace, table_resource_id, region)
        for gsi in global_secondary_index_names:
            delete_application_autoscaling(service_namespace, f"table/{table_name}/index/{gsi}", region)

    except botocore.exceptions.ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ValidationException' and 'has acted as a source region for new replica(s)' in e.response['Error']['Message']:
            tf.failure_print(f"Cannot delete table '{table_name}': It was used to provision replicas in the last 24 hours.\n")
            tf.indent_print("You must either:", 6)
            tf.indent_print("1. Wait 24 hours from the time of provisioning replicas to retry", 8)
            tf.indent_print("2. Delete the replica(s) and/or main table via the AWS console\n", 8)
            return

        else:
            raise

########################### EC2 Service #############################

def deregister_ami(arn: str, region: str) -> None:
    """Deregister and AMI in a given region by ami_id."""

    ami_id = arn.split('/')[-1]

    tf.header_print(f"Deregistering AMI {ami_id} in {region}...")

    client = boto3.client('ec2', region_name=region)
    response = client.deregister_image(ImageId=ami_id)

    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        tf.success_print(f"AMI {ami_id} was successfully deregistered")
    else:
        tf.failure_print(f"AMI {ami_id} was not successfully deregistered")
    tf.response_print(json.dumps(response, indent=4, default=str))


def delete_ec2_instance(arn: str, region: str, autoscaling: bool=False) -> None:
    """
    Terminate an EC2 instance in a given region by a given ARN

    Can be called by the main delete function or by delete_autoscaling_group.

    1. A describe_instance request is first made to check if the instance exists and has not already been terminated.
    2. If it hasn't, the termination request is made.
    3. If the instance was not terminated as part of an autoscaling group deletion, the ec2_waiter function is called to ensure the instance is
    fully terminated to avoid any dependency issues.
    4. If the instance was terminated as part of an autoscaling group deletion, the ec2_waiter function is called by the delete_autoscaling_group
    function instead.

    Args:
        arn (str): The ARN of the EC2 instance to terminate
        region (str): The region the EC2 instance is in
        autoscaling (bool, optional): Whether or not the function was called by delete_autoscaling_group. Defaults to False.
    """

    client = boto3.client('ec2', region_name=region)
    instance_id = arn.split('/')[-1]

    if autoscaling:
        tf.subheader_print(f"Terminating EC2 instance '{instance_id}' in {region}...")
    else:
        tf.header_print(f"Terminating EC2 instance '{instance_id}' in {region}...")

    try:
        response = client.describe_instances(InstanceIds=[instance_id])

    except botocore.exceptions.ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')

        if error_code == 'InvalidInstanceID.NotFound':
            tf.success_print(f"EC2 instance '{instance_id}' not found. It may have already been terminated.\n")
            return

        else:
            tf.failure_print(f"Error describing EC2 instance '{instance_id}': {e}\n")
            raise

    if not response['Reservations']:
        tf.success_print(f"EC2 instance '{instance_id}' not found. It may have already been terminated.\n")
        return

    instance_status = response['Reservations'][0]['Instances'][0]['State']['Name']

    if instance_status in ['terminated', 'shutting-down']:
        tf.success_print(f"Current status of EC2 instance '{instance_id}' is: {instance_status}. Skipping...\n")
        return

    try:
        response = client.terminate_instances(InstanceIds=[instance_id])
        status_code = response['ResponseMetadata']['HTTPStatusCode']

        if 200 <= status_code < 300:
            tf.success_print(f"EC2 instance '{instance_id}' is shutting down.")
        else:
            raise RuntimeError(f"Failed to initiate termination of EC2 instance '{instance_id}': Status Code: {status_code}")

        tf.response_print(json.dumps(response, indent=4, default=str))

        if not autoscaling:
            tf.indent_print(f"Waiting for EC2 instance '{instance_id}' to terminate to avoid dependency violations...\n")
            ec2_waiter([instance_id], region)
            tf.success_print(f"EC2 instance '{instance_id}' has been terminated.")
            print()

    except botocore.exceptions.ClientError as e:
        tf.failure_print(f"ClientError while terminating EC2 instance '{instance_id}':")
        tf.indent_print(e, 6)
        raise

    except Exception as e:
        tf.failure_print(f"Unexpected error while terminating EC2 instance '{instance_id}':")
        tf.indent_print(e, 6)
        raise


def ec2_waiter(instance_ids: list[str], region: str) -> None:
    """Wait for list of EC2 instances to be fully terminated."""

    client = boto3.client('ec2', region_name=region)
    waiter = client.get_waiter('instance_terminated')
    waiter.wait(
        InstanceIds=instance_ids,
        WaiterConfig={
            'Delay': 15,
            'MaxAttempts': 20
        }
    )


def release_eip(arn: str, region: str) -> None:
    """Release an elastic IP address in a given region by ARN."""

    tf.header_print(f"Releasing Elastic IP {arn} in {region}...")
    client = boto3.client('ec2', region_name=region)
    allocation_id = arn.split('/')[-1]
    response = client.release_address(AllocationId=allocation_id)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        tf.success_print(f"Elastic IP {allocation_id} was successfully released")
    else:
        tf.failure_print(f"Elastic IP {allocation_id} was not successfully released")
    tf.response_print(json.dumps(response, indent=4, default=str))


def delete_internet_gateway(arn: str, region: str) -> None:
    """
    Delete an internet gateway in a given region by ARN.

    Checks for any attached VPCs and detaches the gateway from the VPC before deleting it.
    If no VPCs are attached, the gateway is deleted immediately.

    Args:
        arn (str): The ARN of the internet gateway to delete
        region (str): The region the internet gateway is in
    """

    client = boto3.client('ec2', region_name=region)
    gateway_id = arn.split('/')[-1]
    tf.header_print(f"Deleting Internet Gateway {gateway_id} in {region}...")

    # Detach Internet Gateway if it is attached to a VPC
    tf.subheader_print("Checking for VPC attachments...")
    try:
        response = client.describe_internet_gateways(InternetGatewayIds=[gateway_id])
        attachments = response.get('InternetGateways', [])[0].get('Attachments', [])

        for attachment in attachments:
            vpc_id = attachment.get('VpcId')
            if vpc_id:
                client.detach_internet_gateway(InternetGatewayId=gateway_id, VpcId=vpc_id)
                tf.success_print(f"Internet Gateway {gateway_id} was successfully detached from VPC {vpc_id}")

    except botocore.exceptions.ClientError as e:
        tf.failure_print(f"Failed to detach Internet Gateway {gateway_id}, error: {str(e)}")
        return

    print()

    # Delete Internet Gateway after it has been detached
    tf.subheader_print("Proceeding with deletion...")
    try:
        response = client.delete_internet_gateway(InternetGatewayId=gateway_id)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.success_print(f"Internet gateway {gateway_id} was successfully deleted")
        else:
            tf.failure_print(f"Internet gateway {gateway_id} was not successfully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))

    except botocore.exceptions.ClientError as e:
        tf.failure_print(f"Failed to delete {gateway_id}: {str(e)}\n")


def delete_launch_template(arn: str, region: str) -> None:
    """
    Delete a launch template in a given region by ARN

    Args:
        arn (str): The ARN of the launch template to delete
        region (str): The region the launch template is in

    Returns:
        None

    Raises:
        botocore.exceptions.ClientError: Any client errors that occur during the process
    """

    client = boto3.client('ec2', region_name=region)
    template_id = arn.split('/')[-1]

    tf.header_print(f"Deleting Launch Template {template_id} in {region}...")

    try:
        response = client.delete_launch_template(LaunchTemplateId=template_id)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.success_print(f"Launch template {template_id} was successfully deleted")
        else:
            tf.failure_print(f"Launch template {template_id} was not successfully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))

    except botocore.exceptions.ClientError:
        raise


def delete_nat_gateway(arn: str, region: str) -> None:
    """
    Delete a NAT gateway in a given region by ARN.

    First checks to see if NAT Gateway was already deleted, or is in the process of deleting. If the
    NAT Gateway has not already been deleted, the function will initiate the deletion process and
    use a waiter to wait for the NAT GW to be fully deleted.

    Args:
        arn (str): The ARN of the NAT gateway to delete
        region (str): The region the NAT gateway is in
    """

    client = boto3.client('ec2', region_name=region)
    nat_gateway_id = arn.split('/')[-1]
    tf.header_print(f"Deleting Nat Gateway {nat_gateway_id} in {region}...")
    deleted = client.describe_nat_gateways(NatGatewayIds=[nat_gateway_id])['NatGateways'][0]['State']

    # consider calling the waiter here if status is 'deleting'
    if deleted == 'deleted' or deleted == 'deleting':
        tf.success_print(f"Nat gateway {nat_gateway_id} was already deleted")
        return
    try:
        response = client.delete_nat_gateway(NatGatewayId=nat_gateway_id)
        tf.indent_print(f"Nat gateway {nat_gateway_id} deletion initiated")
        tf.indent_print("Waiting for NAT Gateway to complete deletion process...\n")
        nat_deleted = client.get_waiter('nat_gateway_deleted')
        nat_deleted.wait(
            NatGatewayIds=[nat_gateway_id],
            WaiterConfig={
                'Delay': 10,
                'MaxAttempts': 12
            }
        )
        tf.success_print(f"Nat gateway {nat_gateway_id} has been fully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))
    except Exception as e:
        tf.failure_print(f"Nat gateway {nat_gateway_id} was not fully deleted: {e}\n")
        return


def delete_route_table(arn: str, region: str) -> None:
    """Delete a route table in a given region by ARN."""

    client = boto3.client('ec2', region_name=region)
    route_table_id = arn.split('/')[-1]
    tf.header_print(f"Deleting route table {route_table_id} in {region}...")

    response = client.delete_route_table(RouteTableId=route_table_id)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        tf.success_print(f"Route table {route_table_id} was successfully deleted")
    else:
        tf.failure_print(f"Route table {route_table_id} was not successfully deleted")
    tf.response_print(json.dumps(response, indent=4, default=str))


# May need to add a step to detach from VPC to avoid dependency issues
def delete_security_group(arn: str, region: str, vpc_funct: bool=False) -> None:
    """
    Delete a security group in a given region by ARN

    Args:
        arn (str): The ARN of the security group to delete
        region (str): The region the security group is in
        vpc_funct: (bool, optional): Whether or not the function was called by delete_vpc. Defaults to False.

    Returns:
        None

    Raises:
        botocore.exceptions.ClientError: Any client errors that occur during the process
    """

    client = boto3.client('ec2', region_name=region)
    sg_id = arn.split('/')[-1]

    if vpc_funct:
        tf.subheader_print(f"Deleting security group '{sg_id}' in {region}...")
    else:
        tf.header_print(f"Deleting security group '{sg_id}' in {region}...")

    try:
        response = client.delete_security_group(GroupId=sg_id)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.success_print(f"Security group {sg_id} was successfully deleted")
        else:
            tf.failure_print(f"Security group {sg_id} was not successfully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))

    except:
        raise



def delete_snapshot(arn: str, region: str) -> None:
    """Delete a snapshot in a given region by ARN."""

    snapshot_id = arn.split('/')[-1]

    tf.header_print(f"Deleting snapshot {snapshot_id} in {region}...")

    client = boto3.client('ec2', region_name=region)
    try:
        response = client.delete_snapshot(SnapshotId=snapshot_id)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.success_print(f"Snapshot {snapshot_id} was successfully deleted")
        else:
            tf.failure_print(f"Snapshot {snapshot_id} was not successfully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))

    except botocore.exceptions.ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')

        if error_code == 'InvalidSnapshot.NotFound':
            tf.success_print(f"Snapshot '{snapshot_id}' not found. It may have already been deleted.\n")
            return

        else:
            raise


# TODO: Add a check for hanging ENIs
def delete_subnet(arn: str, region: str) -> None:
    """
    Delete a subnet in a given region by ARN.

    1. Checks for any route tables associations that may exist
    2. Disassociates the subnet from any route tables if the associations exist
    3. Deletes subnet

    Args:
        arn (str): The ARN of the subnet to delete
        region (str): The region the subnet is in
    """

    client = boto3.client('ec2', region_name=region)
    subnet_id = arn.split('/')[-1]

    tf.header_print(f"Deleting subnet {subnet_id} in {region}...")

    # Find any route tables associated with the subnet and detach them
    tf.indent_print("Looking for associated route tables...\n")
    route_tables = client.describe_route_tables(Filters=[{'Name': 'association.subnet-id', 'Values': [subnet_id]}])['RouteTables']
    associations = [
        {
            "route_table_id": rt["RouteTableId"],
            "association_id": assoc["RouteTableAssociationId"]
        }
        for rt in route_tables
        for assoc in rt.get("Associations", [])
        if assoc.get("SubnetId") == subnet_id
    ]

    # Disassociate route tables from subnet if they are associated
    if associations:
        tf.indent_print(f"Route tables associated with subnet {subnet_id}:\n")
        for rt in associations:
            tf.indent_print(rt['route_table_id'], indent=6)
        print()
        tf.indent_print(f"Disassociating route tables from subnet {subnet_id}...")
        for rt in associations:
            response = client.disassociate_route_table(AssociationId=rt['association_id'])
            if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
                tf.success_print(f"Route table {rt['route_table_id']} was successfully disassociated from subnet {subnet_id}")
            else:
                tf.failure_print(f"Route table {rt['route_table_id']} was not successfully disassociated from subnet {subnet_id}")
            tf.response_print(json.dumps(response, indent=4, default=str))

    # # Check for any ENIs in the subnet
    # enis = client.describe_network_interfaces(Filters=[{'Name': 'subnet-id', 'Values': [subnet_id]}])['NetworkInterfaces']
    # interface_enis = [eni for eni in enis if eni["InterfaceType"] == "interface"]
    # if interface_enis:
    #     print(f"Subnet {subnet_id} contains the following Elastic Network Interfaces (ENIs):\n")
    #     for eni in interface_enis:
    #         print(eni['NetworkInterfaceId'])
    #     print(f"\nDetaching ENIs from subnet {subnet_id}...")
    #     for eni in interface_enis:
    #         response = client.detach_network_interface(AttachmentId=eni['Attachment']['AttachmentId'], Force=True)
    #         if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
    #             print(f"\nENI {eni['NetworkInterfaceId']} was successfully detached from subnet {subnet_id}")
    #         else:
    #             print(f"\nENI {eni['NetworkInterfaceId']} was not successfully detached from subnet {subnet_id}")
    #         tf.indent_print(json.dumps(response, indent=4, default=str))


    # Delete subnet
    tf.indent_print("Initiating subnet deletion...\n")
    response = client.delete_subnet(SubnetId=subnet_id)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        tf.success_print(f"Subnet {subnet_id} was successfully deleted")
    else:
        tf.failure_print(f"Subnet {subnet_id} was not successfully deleted")
    tf.response_print(json.dumps(response, indent=4, default=str))


def delete_vpc_endpoint(arn: str, region: str) -> None:
    """
    Delete a VPC endpoint in a given region by ARN

    If deletion is unsuccessful, a check is made to see if the VPC endpoint was already deleted.
    If it was, a success message is printed, otherwise the error is printed.

    Args:
        arn (str): The ARN of the VPC endpoint to delete
        region (str): The region the VPC endpoint is in
    """

    client = boto3.client('ec2', region_name=region)
    endpoint_id = arn.split('/')[-1]
    tf.header_print(f"Deleting VPC endpoint {endpoint_id} in {region}...")
    try:
        response = client.delete_vpc_endpoints(VpcEndpointIds=[endpoint_id])

        if 'Unsuccessful' in response:
            for error in response['Unsuccessful']:
                error_code = error.get('Error', {}).get('Code')
                error_msg = error.get('Error', {}).get('Message', 'No message provided')
                resource_id = error.get('ResourceId', endpoint_id)

                # Handle specific known error
                if error_code == 'InvalidVpcEndpoint.NotFound':
                    tf.success_print(f"VPC endpoint {resource_id} was already deleted.")
                else:
                    tf.failure_print(f"Failed to delete VPC endpoint {resource_id}: {error_code} - {error_msg}")
                tf.response_print(json.dumps(response, indent=4, default=str))
                return

        # If deletion is successful
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.success_print(f"VPC endpoint {endpoint_id} was successfully deleted")
        else:
            tf.failure_print(f"VPC endpoint {endpoint_id} was not successfully delete")
        tf.response_print(json.dumps(response, indent=4, default=str))

    except botocore.exceptions.ClientError as e:
        tf.failure_print(f"Failed to delete VPC endpoint {endpoint_id}: {str(e)}\n")
        return None


def delete_vpc(arn: str, region: str) -> list[dict] | None:
    """
    Deletes a VPC and all of its security groups in a given region by ARN

    First checks to see if the VPC contains any security groups and deletes them first.
    Then the VPC is deleted.

    Args:
        arn (str): The ARN of the VPC to delete
        region (str): The region the VPC is in

    Returns:
        list[dict] | None: Retryable security groups that could not be deleted, or None if they were all successfully deleted
    """

    client = boto3.client('ec2', region_name=region)
    vpc_id = arn.split('/')[-1]
    tf.header_print(f"Deleting VPC {vpc_id} in {region}...")
    tf.subheader_print(f"Checking VPC {vpc_id} for security groups...")

    response = client.describe_security_groups(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    security_groups = response['SecurityGroups']

    security_group_retries = []
    for sg in security_groups:
        if sg['GroupName'] == 'default':
            continue

        sg_arn = sg.get("SecurityGroupArn")
        if not sg_arn:
            sg_arn = f"arn:aws:ec2:{region}:{sg['OwnerId']}:security-group/{sg['GroupId']}"

        try:
            delete_security_group(sg_arn, region, True)

        except botocore.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'InvalidGroup.NotFound':
                tf.success_print(f"Security group {sg_arn} already deleted.")
                continue
            else:
                tf.failure_print(f"Error deleting security group {sg_arn}: {e}")
                security_group_retries.append({
                    "resource_type": "security_group",
                    "service": "ec2",
                    "region": region,
                    "resource_id": sg_arn
                })

    tf.subheader_print("Deleting VPC...")
    print()
    try:
        response = client.delete_vpc(VpcId=vpc_id)
        status_code = response['ResponseMetadata']['HTTPStatusCode']

        if 200 <= status_code < 300:
            tf.success_print(f"VPC {vpc_id} was successfully deleted")
        else:
            tf.failure_print(f"VPC {vpc_id} was not successfully deleted")
            tf.response_print(json.dumps(response, indent=4, default=str))
            raise botocore.exceptions.ClientError(
                error_response={"Error": {"Code": "DependencyViolation", "Message": "VPC deletion failed"}},
                operation_name="DeleteVpc"
            )

        tf.response_print(json.dumps(response, indent=4, default=str))

    except botocore.exceptions.ClientError:
        raise

    if security_group_retries:
        return security_group_retries


########################## ELBv2 Service ############################

def delete_elastic_load_balancer(arn: str, region: str) -> None:
    """
    Delete an Elastic Load Balancer in a given region by ARN

    1. Checks to see if the ELB has any listeners or target groups associated with it
    2  Checks to see if the target groups are attached to other ELBs
    3. If target groups are attached to other ELBs, the ELB will not be deleted
    4. User is prompted to confirm deletion of listeners and target groups
    5. If target groups are not attached to other ELBs and confirmation is given: the listeners, target groups and finally the ELB are deleted
    6. After deletion is initiated, a waiter is used to ensure the ELB is fully deleted before exiting the function

    Args:
        arn (str): The ARN of the ELB to delete
        region (str): The region the ELB is in
    """

    tf.header_print(f"Deleting ELB {arn} in {region}...")
    client = boto3.client('elbv2', region_name=region)

    tf.indent_print("Checking ELB for listeners and target groups...\n")
    response = client.describe_listeners(LoadBalancerArn=arn)
    listeners = response['Listeners']
    listener_arns = [listener['ListenerArn'] for listener in listeners]

    target_group_arns = set()
    for listener in listeners:
        for action in listener.get('DefaultActions', []):
            if action['Type'] == 'forward':
                forward_config = action.get("ForwardConfig", {})
                for tg in forward_config.get("TargetGroups", []):
                    target_group_arns.add(tg['TargetGroupArn'])

    # Check if target groups are attached to other ELBs and exit if they are
    tgs_attached_to_other_elbs = []
    for tg_arn in target_group_arns:
        tg_info = client.describe_target_groups(TargetGroupArns=[tg_arn])['TargetGroups'][0]
        if len(tg_info['LoadBalancerArns']) > 1:
            tgs_attached_to_other_elbs.append(tg_arn)

    if tgs_attached_to_other_elbs:
        tf.indent_print("The following target groups are used by other ELBs and will not be deleted:\n")
        for tg in tgs_attached_to_other_elbs:
            tf.indent_print(tg, 6)
        tf.indent_print(f"ELB {arn} cannot be deleted at this time. Exiting...\n")
        return

    # Confirm deletion of listeners and target groups
    tf.subheader_print(f"Proceeding with deleting ELB {arn} will also delete the following listeners and target groups:")
    tf.subheader_print("Listeners:", 6)
    for listener in listener_arns:
        tf.indent_print(listener, 8)
    print()
    tf.subheader_print("Target groups:", 6)
    for tg in target_group_arns:
        tf.indent_print(tg, 8)
    print()
    delete_tgs_and_listeners = tf.y_n_prompt("Proceed with deletion process?")
    print()

    if delete_tgs_and_listeners != 'y':
        tf.indent_print("Skipping ELB deletion...")
        return

    # Delete listeners
    # TODO: Modify to use the delete_listener function instead
    tf.indent_print("Deleting target groups and listeners...")
    for listener in listener_arns:
        response = client.delete_listener(ListenerArn=listener)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.success_print(f"Listener {listener} was successfully deleted")
        else:
            tf.failure_print(f"Listener {listener} was not successfully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))

    # Delete target groups
    # TODO: Modify to use the delete_target_group function instead
    tf.indent_print("Deleting target groups...")
    for tg in target_group_arns:
        response = client.delete_target_group(TargetGroupArn=tg)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.success_print(f"Target group {tg} was successfully deleted")
        else:
            tf.failure_print(f"Target group {tg} was not successfully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))

    # Delete load balancer
    tf.indent_print("Initiating ELB deletion...")
    response = client.delete_load_balancer(LoadBalancerArn=arn)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        tf.success_print(f"Deletion of load balancer {arn} was successfully initiated")
    else:
        tf.failure_print(f"Deletion of load balancer {arn} was not successfully initiated")
    tf.response_print(json.dumps(response, indent=4, default=str))

    # Check to make sure load balancer is fully deleted
    print()
    tf.indent_print(f"Waiting for ELB {arn} to be fully deleted...")
    load_balancer_deleted = client.get_waiter('load_balancers_deleted')
    try:
        load_balancer_deleted.wait(
            LoadBalancerArns=[arn],
            WaiterConfig={'Delay': 10, 'MaxAttempts': 12}
        )
        tf.success_print(f"Load balancer {arn} has been fully deleted")
    except botocore.exceptions.WaiterError as e:
        tf.failure_print(f"Load balancer {arn} has not been fully deleted: {e}")

    print()

# TODO: This should probably be modified to be able to be called from the delete ELB function as well
# Can be achieved by modifying the header print statement to be a subheader if called by delete ELB
def delete_listener(arn: str, region: str) -> None:
    """
    Delete listener in a given region by ARN

    Args:
        arn (str): The ARN of the listener to delete
        region (str): The region the listener is in
    """

    client = boto3.client('elbv2', region_name=region)
    try:
        tf.header_print(f"Deleting listener {arn} in {region}...")
        response = client.delete_listener(ListenerArn=arn)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            print(f"Listener {arn} was successfully deleted")
        else:
            print(f"Listener {arn} was not successfully deleted")
        tf.indent_print(json.dumps(response, indent=4, default=str))

    except client.exceptions.ListenerNotFoundException:
        tf.indent_print(f"Listener {arn} was not found and may have already been deleted")

    print()

# TODO: This should probably be modified to be able to be called from the delete ELB function as well
# Can be achieved by modifying the header print statement to be a subheader if called by delete ELB
def delete_target_group(arn: str, region: str) -> None:
    """
    Delete target group in a given region by ARN

    Args:
        arn (str): The ARN of the target group to delete
        region (str): The region the target group is in
    """
    client = boto3.client('elbv2', region_name=region)
    try:
        tf.header_print(f"Deleting target group {arn} in {region}...")
        response = client.delete_target_group(TargetGroupArn=arn)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.indent_print(f"Target group {arn} was successfully deleted")
        else:
            tf.indent_print(f"Target group {arn} was not successfully deleted")
        tf.indent_print(json.dumps(response, indent=4, default=str))

    except client.exceptions.TargetGroupNotFoundException:
        tf.indent_print(f"Target group {arn} was not found and may have already been deleted")

    print()

########################### IAM Service #############################

######################### Lambda Service ############################

def delete_lambda_function(arn: str, region: str) -> None:
    tf.header_print(f"Deleting Lambda function {arn} in {region}...")
    client = boto3.client('lambda', region_name=region)
    response = client.delete_function(FunctionName=arn)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        tf.indent_print(f"Lambda function {arn} was successfully deleted")
    else:
        tf.indent_print(f"Lambda function {arn} was not successfully deleted")
    tf.indent_print(json.dumps(response, indent=4, default=str))

    print()

########################### S3 Service ##############################

def delete_s3_bucket(arn: str, region: str) -> None:
    '''
    Checks to see if bucket has objects. If it does, the user will be prompted if they really
    want to delete the bucket and all of its objects. Works with versioned as well as unversioned buckets.
    '''
    client = boto3.client('s3', region_name=region)
    bucket_name = arn.split(':')[-1]

    try:
        tf.header_print(f"Deleting S3 bucket {bucket_name} in {region}...")
        # Check if versioning is enabled
        versioning = client.get_bucket_versioning(Bucket=bucket_name)
        is_versioned = versioning.get('Status') == 'Enabled'

        has_objects = False

        if is_versioned:
            response = client.list_object_versions(Bucket=bucket_name, MaxKeys=1)
            has_objects = 'Versions' in response or 'DeleteMarkers' in response
        else:
            response = client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
            has_objects = 'Contents' in response

        if has_objects:
            confirm = tf.warning_confirmation(f'S3 bucket {bucket_name} is not empty. Are you sure you want to delete all contents and the bucket?')
            if confirm != 'yes':
                tf.indent_print(f"Skipping deletion of bucket '{bucket_name}'.")
                return

            tf.indent_print(f"Emptying bucket '{bucket_name}'...")

            if is_versioned:
                paginator = client.get_paginator('list_object_versions')
                for page in paginator.paginate(Bucket=bucket_name):
                    objects_to_delete = []
                    for version in page.get('Versions', []):
                        objects_to_delete.append({'Key': version['Key'], 'VersionId': version['VersionId']})
                    for marker in page.get('DeleteMarkers', []):
                        objects_to_delete.append({'Key': marker['Key'], 'VersionId': marker['VersionId']})
                    if objects_to_delete:
                        response = client.delete_objects(Bucket=bucket_name, Delete={'Objects': objects_to_delete})
                        errors = response.get('Errors', [])
                        if errors:
                            tf.indent_print(f"One or more objects in {bucket_name} encountered errors during the deletion process:")
                            tf.indent_print(json.dumps(errors, indent=4, default=str))
                            tf.indent_print("Bucket cannot be deleted at this time. Exiting...")
                            print()
                            return

            else:
                paginator = client.get_paginator('list_objects_v2')
                for page in paginator.paginate(Bucket=bucket_name):
                    objects_to_delete = [{'Key': obj['Key']} for obj in page.get('Contents', [])]
                    if objects_to_delete:
                        client.delete_objects(Bucket=bucket_name, Delete={'Objects': objects_to_delete})

        # Delete the bucket
        tf.indent_print(f"Deleting bucket '{bucket_name}'...")
        response = client.delete_bucket(Bucket=bucket_name)
        tf.success_print(f"\nS3 bucket '{bucket_name}' successfully deleted.")
        tf.indent_print(json.dumps(response, indent=4, default=str))

    except client.exceptions.NoSuchBucket:
        tf.header_print(f"Bucket {bucket_name} in {region} does not exist.")
    except Exception as e:
        tf.header_print(f"Error deleting S3 bucket {bucket_name} in {region}: {e}")

########################## SNS Service ##############################

def delete_sns_topic(arn: str, region: str) -> None:
    client = boto3.client('sns', region_name=region)
    topic_arn = arn
    tf.header_print(f"Deleting SNS topic {topic_arn} in {region}...")

    response = client.list_subscriptions_by_topic(TopicArn=topic_arn)
    subscriptions = response.get('Subscriptions', [])
    if subscriptions:
        tf.indent_print(f"{tf.Format.yellow}SNS topic has the following subscriptions:{tf.Format.end}")
        for subscription in subscriptions:
            tf.indent_print(json.dumps(subscription, indent=4, default=str), 6)
        confirm = tf.y_n_prompt("Do you wish to proceed with deleting the topic and all of its subscriptions?")

        if confirm != 'y':
            tf.indent_print("Skipping SNS topic deletion...\n")
            return

    print()
    response = client.delete_topic(TopicArn=topic_arn)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        tf.success_print(f"SNS topic {topic_arn} was successfully deleted")
    else:
        tf.failure_print(f"SNS topic {topic_arn} was not successfully deleted")
    tf.response_print(json.dumps(response, indent=4, default=str))


########################## SQS Service ##############################

def delete_sqs_queue(arn: str, region: str) -> None:
    client = boto3.client('sqs', region_name=region)
    queue_name = arn.split(':')[-1]
    tf.header_print(f"Deleting SQS queue {queue_name} in {region}...")
    queue_url = client.get_queue_url(QueueName=queue_name)['QueueUrl']
    response = client.delete_queue(QueueUrl=queue_url)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        tf.success_print(f"SQS queue {arn} was successfully deleted")
    else:
        tf.failure_print(f"SQS queue {arn} was not successfully deleted")
    tf.response_print(json.dumps(response, indent=4, default=str))
