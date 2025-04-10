'''
Contains the delete functions as well as the DELETE_FUNCTIONS dictionary, which maps resource and service
to the appropriate individual delete function.
'''

import time
import json
import botocore.exceptions
import boto3
import text_formatting as tf


#######################################################################
# Individual Deletion Functions
#######################################################################

######################### API GW Services ###########################

# This has been tested and works. The same logic needs to be updated for the REST API function.
def delete_api(arn, region):
    '''
    Handles HTTP APIs and WebSocket APIs. Checks for any associated VPC links and optionally deletes them.
    If VPC links exist and are deleted, the function waits for them to become inactive or non-existent before proceeding.
    '''
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
            tf.success_print(f"API {arn} was successfully deleted")
        else:
            tf.failure_print(f"API {arn} was not successfully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))
    except botocore.exceptions.ClientError as e:
        tf.failure_print(f"Failed to delete API {arn}: {e}\n")

    print()
    # Ask if user wants to delete associated VPC links if there are any
    delete_vpc_links = 'n'
    if vpc_link_ids:
        delete_vpc_links = tf.prompt(f'Found {len(vpc_link_ids)} VPC link(s) associated with API {arn}. Delete them?')
        print()
        if delete_vpc_links != 'y':
            tf.indent_print("VPC links will not be deleted")
            return
        else:
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
                    tf.failure_print(f"Error deleting VPC link {vpc_link_id}: {e}\n")

    # Exit if no VPC links were found
    else:
        return

    # Wait for VPC links to become inactive (avoid dependency issues)
    if vpc_link_ids and delete_vpc_links == 'y':
        tf.indent_print("Checking status(es) of VPC link(s) to avoid dependency violations...\n")
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

# TODO: This still needs to be tested.
def delete_rest_api(arn, region):
    '''
    Handles REST APIs. Checks for any associated VPC links and optionally deletes them.
    If VPC links exist and are deleted, the function waits for them to become fully deleted before proceeding.
    '''
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
        delete_vpc_links = tf.prompt(f"Found {len(vpc_link_ids)} VPC link(s) associated with REST API {arn}. Delete them?")
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


####################### AutoScaling Service #########################

def delete_autoscaling_group(arn, region):
    tf.header_print(f"Deleting autoscaling group {arn} in {region}...")
    client = boto3.client('autoscaling', region_name=region)
    asg_name = arn.split('/')[-1]
    instances = [
        instance["InstanceId"]
        for instance in client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])["AutoScalingGroups"][0]["Instances"]
    ]

    response = client.delete_auto_scaling_group(AutoScalingGroupName=asg_name, ForceDelete=True)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        tf.success_print(f"Autoscaling group {arn} deletion initiated successfully")
    else:
        tf.failure_print(f"Autoscaling group {arn} was not successfully deleted")
    tf.response_print(json.dumps(response, indent=4, default=str))

    # Check to make sure autoscaling instances are fully shut down
    if instances:
        for instance in instances:
            delete_ec2_instance(instance, region, True)
        tf.indent_print("Waiting for autoscaling instances to shut down to avoid dependency violations...")

        ec2_waiter(instances, region)
        tf.success_print("All instances in autoscaling group are terminated.")
        print()

####################### CloudFront Service ##########################

def delete_cloudfront_distribution(arn):
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
    except client.exceptions.DistributionNotDisabled:
        tf.indent_print(f"Distribution {distribution_id} is not yet fully disabled. Will be retried later.\n")
    except Exception as e:
        tf.failure_print(f"Error deleting distribution {distribution_id}: {str(e)}\n")


def disable_cloudfront_distribution(arn):
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


def wait_for_distribution_disabled(arn):
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

def delete_dynamodb_table(arn, region):
    """
    Deletes a DynamoDB table. If the table has deletion protection or items,
    the user will be prompted before proceeding.
    """
    tf.header_print(f"Deleting DynamoDB table {arn} in {region}...")
    client = boto3.client('dynamodb', region_name=region)
    table_name = arn.split('/')[-1]

    # Check for deletion protection
    try:
        table_info = client.describe_table(TableName=table_name)['Table']
    except client.exceptions.ResourceNotFoundException:
        tf.indent_print(f"Table {table_name} does not exist. It's possible that it has been deleted already.")
        return

    deletion_protection = table_info.get('DeletionProtectionEnabled', False)
    if deletion_protection:
        disable_protection = tf.warning_confirmation(f'Table {table_name} has deletion protection enabled. Disable it?')
        if disable_protection != 'yes':
            tf.indent_print(f"Skipping deletion of DynamoDB table {table_name}")
            return

        # Disable deletion protection
        response = client.update_table(
            TableName=table_name,
            DeletionProtectionEnabled=False
        )
        tf.success_print(f"Deletion protection disabled for table {table_name}")
        tf.response_print(json.dumps(response, indent=4, default=str))

    # Check if table has items
    response = client.scan(TableName=table_name, Limit=1)
    if len(response.get('Items', [])) > 0:
        confirm = tf.warning_confirmation(f'Table {table_name} is not empty. Delete all items and the table?')
        if confirm != 'yes':
            tf.indent_print(f"Skipping deletion of DynamoDB table {table_name}")
            return

    # Delete the table
    print()
    try:
        response = client.delete_table(TableName=table_name)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.success_print(f"Table {table_name} was successfully deleted")
        else:
            tf.failure_print(f"Table {table_name} was not successfully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))

    except botocore.exceptions.ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ValidationException' and 'has acted as a source region for new replica(s)' in e.response['Error']['Message']:
            tf.failure_print(f"Cannot delete table {table_name}: It was used to provision replicas in the last 24 hours.\n")
            tf.failure_print("You must either:", 6)
            tf.failure_print("1. Wait 24 hours from the time of provisioning replicas to retry", 8)
            tf.failure_print("2. Delete the replica(s) and/or main table via the AWS console\n", 8)
            return
        else:
            tf.failure_print(f"Error deleting DynamoDB table {table_name}: {e}\n")
            return

########################### EC2 Service #############################

def deregister_ami(arn, region):
    tf.header_print(f"Deregistering AMI {arn} in {region}...")
    client = boto3.client('ec2', region_name=region)
    response = client.deregister_image(ImageId=arn)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        tf.success_print(f"AMI {arn} was successfully deregistered")
    else:
        tf.failure_print(f"AMI {arn} was not successfully deregistered")
    tf.response_print(json.dumps(response, indent=4, default=str))


def delete_ec2_instance(arn, region, autoscaling=False):
    client = boto3.client('ec2', region_name=region)
    instance_id = arn.split('/')[-1]

    if autoscaling:
        tf.indent_print(f"Terminating EC2 instance {instance_id} in {region}...")
    else:
        tf.header_print(f"Terminating EC2 instance {instance_id} in {region}...")

    try:
        response = client.describe_instances(InstanceIds=[instance_id])
    except botocore.exceptions.ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'InvalidInstanceID.NotFound':
            tf.success_print(f"EC2 instance {instance_id} not found. It may have already been terminated.\n")
            return
        else:
            tf.failure_print(f"Error describing EC2 instance {instance_id}: {e}")
            raise
            print()

    if not response['Reservations']:
        tf.success_print(f"EC2 instance {instance_id} not found. It may have already been terminated.\n")
        return

    instance_status = response['Reservations'][0]['Instances'][0]['State']['Name']

    if instance_status in ['terminated', 'shutting-down']:
        tf.success_print(f"Current status of EC2 instance {instance_id} is: {instance_status}. Skipping...\n")
        return

    response = client.terminate_instances(InstanceIds=[instance_id])
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        tf.success_print(f"EC2 instance {instance_id} is shutting down.")
    else:
        tf.failure_print(f"EC2 instance {instance_id} termination was not successfully initiated.")
    tf.response_print(json.dumps(response, indent=4, default=str))

    if not autoscaling:
        ec2_waiter([instance_id], region)
        tf.success_print(f"EC2 instance {instance_id} has been terminated.")
        print()


def ec2_waiter(instance_ids, region):
    client = boto3.client('ec2', region_name=region)
    waiter = client.get_waiter('instance_terminated')
    waiter.wait(
        InstanceIds=instance_ids,
        WaiterConfig={
            'Delay': 15,
            'MaxAttempts': 20
        }
    )


def release_eip(arn, region):
    tf.header_print(f"Releasing Elastic IP {arn} in {region}...")
    client = boto3.client('ec2', region_name=region)
    allocation_id = arn.split('/')[-1]
    response = client.release_address(AllocationId=allocation_id)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        tf.success_print(f"Elastic IP {allocation_id} was successfully released")
    else:
        tf.failure_print(f"Elastic IP {allocation_id} was not successfully released")
    tf.response_print(json.dumps(response, indent=4, default=str))


def delete_internet_gateway(arn, region):
    client = boto3.client('ec2', region_name=region)
    gateway_id = arn.split('/')[-1]
    tf.header_print(f"Deleting Internet Gateway {gateway_id} in {region}...")

    # Detach Internet Gateway if it is attached to a VPC
    tf.indent_print("Checking for VPC attachments...")
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
    tf.indent_print("Proceeding with deletion...")
    try:
        response = client.delete_internet_gateway(InternetGatewayId=gateway_id)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.success_print(f"Internet gateway {gateway_id} was successfully deleted")
        else:
            tf.failure_print(f"Internet gateway {gateway_id} was not successfully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))

    except botocore.exceptions.ClientError as e:
        tf.failure_print(f"Failed to delete {gateway_id}: {str(e)}\n")


def delete_nat_gateway(arn, region):
    client = boto3.client('ec2', region_name=region)
    nat_gateway_id = arn.split('/')[-1]
    tf.header_print(f"Deleting Nat Gateway {nat_gateway_id} in {region}...")
    deleted = client.describe_nat_gateways(NatGatewayIds=[nat_gateway_id])['NatGateways'][0]['State']
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


def delete_route_table(arn, region):
    client = boto3.client('ec2', region_name=region)
    route_table_id = arn.split('/')[-1]
    tf.header_print(f"Deleting route table {route_table_id} in {region}...")

    response = client.delete_route_table(RouteTableId=route_table_id)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        tf.success_print(f"Route table {route_table_id} was successfully deleted")
    else:
        tf.failure_print(f"Route table {route_table_id} was not successfully deleted")
    tf.response_print(json.dumps(response, indent=4, default=str))


def delete_snapshot(arn, region):
    tf.header_print(f"Deleting snapshot {arn} in {region}...")
    client = boto3.client('ec2', region_name=region)
    response = client.delete_snapshot(SnapshotId=arn)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        tf.success_print(f"Snapshot {arn} was successfully deleted")
    else:
        tf.failure_print(f"Snapshot {arn} was not successfully deleted")
    tf.response_print(json.dumps(response, indent=4, default=str))


# TODO: Add a check for hanging ENIs
def delete_subnet(arn, region):
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


def delete_vpc_endpoint(arn, region):
    client = boto3.client('ec2', region_name=region)
    endpoint_id = arn.split('/')[-1]
    tf.header_print(f"Deleting VPC endpoint {endpoint_id} in {region}...")
    try:
        response = client.delete_vpc_endpoints(VpcEndpointIds=[endpoint_id])

        if 'Unsuccessful' in response:
            for error in response['Unsuccessful']:
                error_code = error.get('Error', {}).get('Code')
                error_msg = error.get('Error', {}).get('Message', 'No message provided')
                resource_id = error.get('ResourceId', endpoint_id)  # fallback to the one you passed in

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


def delete_vpc(arn, region):
    client = boto3.client('ec2', region_name=region)
    vpc_id = arn.split('/')[-1]
    tf.header_print(f"Deleting VPC {vpc_id} in {region}...")
    tf.indent_print((f"Checking VPC {vpc_id} for security groups...\n"))
    response = client.describe_security_groups(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    security_groups = response['SecurityGroups']
    for sg in security_groups:
        if sg['GroupName'] == 'default':
            continue
        sg_id = sg['GroupId']
        tf.indent_print(f"Deleting security group {sg_id}...")
        response = client.delete_security_group(GroupId=sg_id)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.success_print(f"Security group {sg_id} was successfully deleted")
        else:
            tf.failure_print(f"Security group {sg_id} was not successfully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))

    response = client.delete_vpc(VpcId=vpc_id)
    tf.indent_print("Deleting VPC...")
    print()
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        tf.success_print(f"VPC {vpc_id} was successfully deleted")
    else:
        tf.failure_print(f"VPC {vpc_id} was not successfully deleted")
    tf.response_print(json.dumps(response, indent=4, default=str))


########################## ELBv2 Service ############################

def delete_elastic_load_balancer(arn, region):
    '''
    Deletes ELB as well as any listeners and target groups.
    Handles all types of ELBs besides classic.
    '''
    tf.header_print(f"Deleting ELB {arn} in {region}...")
    client = boto3.client('elbv2', region_name=region)

    tf.indent_print("Checking ELB for listeners and target groups...")
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
            tf.indent_print(tg, indent=6)
        tf.indent_print(f"ELB {arn} cannot be deleted at this time. Exiting...\n")
        return

    # Confirm deletion of listeners and target groups
    tf.indent_print(f"Proceeding with deleting ELB {arn} will also delete the following listeners and target groups:\n")
    tf.indent_print("Listeners:", indent=6)
    for listener in listener_arns:
        tf.indent_print(listener, indent=8)
    tf.indent_print("Target groups:", indent=6)
    for tg in target_group_arns:
        tf.indent_print(tg, indent=8)
    print()
    delete_tgs_and_listeners = tf.prompt("Proceed?")

    if delete_tgs_and_listeners != 'y':
        tf.indent_print("Skipping ELB deletion...")
        return

    # Delete listeners
    tf.indent_print("Deleting target groups and listeners...")
    for listener in listener_arns:
        response = client.delete_listener(ListenerArn=listener)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            tf.success_print(f"Listener {listener} was successfully deleted")
        else:
            tf.failure_print(f"Listener {listener} was not successfully deleted")
        tf.response_print(json.dumps(response, indent=4, default=str))

    # Delete target groups
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


def delete_listener(arn, region):
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


def delete_target_group(arn, region):
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

def delete_lambda_function(arn, region):
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

def delete_s3_bucket(arn, region):
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

def delete_sns_topic(arn, region):
    client = boto3.client('sns', region_name=region)
    topic_arn = arn
    tf.header_print(f"Deleting SNS topic {topic_arn} in {region}...")

    response = client.list_subscriptions_by_topic(TopicArn=topic_arn)
    subscriptions = response.get('Subscriptions', [])
    if subscriptions:
        tf.indent_print(f"{tf.Format.yellow}SNS topic has the following subscriptions:{tf.Format.end}")
        for subscription in subscriptions:
            tf.indent_print(json.dumps(subscription, indent=4, default=str), 6)
        confirm = tf.prompt("Do you wish to proceed with deleting the topic and all of its subscriptions?")

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

def delete_sqs_queue(arn, region):
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

###################################################################
# Delete function mappings
###################################################################

DELETE_FUNCTIONS = {
    'apigateway': {
        'restapi': delete_rest_api # For REST APIs
    },
    'apigatewayv2': {
        'api': delete_api # For HTTP and websocket APIs
    },
    'autoscaling': {
        'autoscalinggroup': delete_autoscaling_group
    },
    'certificatemanager': {
        'certificate': lambda resource: print("deleting certificate"),  # delete_certificate(resource['arn'])
    },
    'cloudfront': {
        'distribution': delete_cloudfront_distribution,  # delete_distribution(resource['arn'])
    },
    'dynamodb': {
        'table': delete_dynamodb_table
    },
    'ec2': {
        'ami': deregister_ami,
        'eip': release_eip,
        'instance': delete_ec2_instance,
        'internetgateway': delete_internet_gateway,
        'natgateway': delete_nat_gateway,  # delete_nat_gateway(resource['arn'])
        'route': lambda resource: print("deleting route"),  # delete_route(resource['arn'])
        'routetable': delete_route_table,
        'security_group': lambda resource: print("deleting security group"),  # delete_security_group(resource['arn'])
        'snapshot': delete_snapshot,
        'subnet': delete_subnet,
        'transitgatewayattachment': lambda resource: print("deleting transit gateway attachment"),  # delete_transit_gateway_vpc_attachment(resource['arn'])
        'vpc': delete_vpc,
        'vpcendpoint': delete_vpc_endpoint,
        'vpcpeering': lambda resource: print("deleting vpc peering"),  # delete_vpc_peering_connection(resource['arn'])
    },
    'elasticloadbalancingv2': {
        'loadbalancer': delete_elastic_load_balancer,
        'listener': delete_listener,
        'targetgroup': delete_target_group,
    },
    # 'iam': {
    #     'managedpolicy': lambda resource: print("deleting managed policy"),  # delete_managed_policy(resource['arn'])
    #     'policy': lambda resource: print("deleting policy"),  # delete_policy(resource['arn'])
    #     'role': lambda resource: print("deleting role"),  # delete_role(resource['arn'])
    # },
    'kms': {
        'key': lambda resource: print("deleting key"),  # delete_key(resource['arn'])
    },
    'lambda': {
        'function': delete_lambda_function
    },
    'rds': {
        'dbinstance': lambda resource: print("deleting db instance"),  # delete_db_instance(resource['arn'])
    },
    'route53': {
        'hostedzone': lambda resource: print("deleting hosted zone"),  # delete_hosted_zone(resource['arn'])
    },
    's3': {
        'bucket': delete_s3_bucket
    },
    'secretsmanager': {
        'secret': lambda resource: print("deleting secret"),  # delete_secret(resource['arn'])
    },
    'sns': {
        'topic': delete_sns_topic
    },
    'sqs': {
        'queue': delete_sqs_queue
    }
}

