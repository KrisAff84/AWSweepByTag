'''
Contains the delete functions as well as the DELETE_FUNCTIONS dictionary, which maps resource and service
to the appropriate individual delete function.
'''

import time
import json
import botocore.exceptions
import boto3

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
    print(f"Deleting HTTP API {arn}...\n")
    client = boto3.client('apigatewayv2', region_name=region)
    api_id = arn.split('/')[-1]

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
            print(f"HTTP API {arn} was successfully deleted")
        else:
            print(f"HTTP API {arn} was not successfully deleted")
        print(json.dumps(response, indent=4, default=str))
        print()
    except botocore.exceptions.ClientError as e:
        print(f"Failed to delete API {arn}: {e}\n")

    print()
    # Ask if user wants to delete associated VPC links if there are any
    delete_vpc_links = 'n'
    if vpc_link_ids:
        delete_vpc_links = input(f"Found {len(vpc_link_ids)} VPC link(s) associated with API {arn}. Delete them? (y/n): ").strip().lower()
        print()
        if delete_vpc_links != 'y':
            print("VPC links will not be deleted")
            return
        else:
            for vpc_link_id in vpc_link_ids:
                try:
                    response = client.delete_vpc_link(VpcLinkId=vpc_link_id)
                    status_code = response['ResponseMetadata']['HTTPStatusCode']
                    if 200 <= status_code < 300:
                        print(f"VPC link {vpc_link_id} was successfully deleted")
                    else:
                        print(f"VPC link {vpc_link_id} was not successfully deleted")
                    print(json.dumps(response, indent=4, default=str))
                    print()
                except botocore.exceptions.ClientError as e:
                    print(f"Error deleting VPC link {vpc_link_id}: {e}\n")

    # Exit if no VPC links were found
    else:
        return

    print()
    # Wait for VPC links to become inactive (avoid dependency issues)
    if vpc_link_ids and delete_vpc_links == 'y':
        print("Checking status(es) of VPC link(s) to avoid dependency violations...\n")
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
                        print(f"VPC link {vpc_link_id} is already deleted")
                    else:
                        print(f"Error checking status for VPC link {vpc_link_id}: {e}")
                        all_inactive = False

            if all_inactive:
                print("All VPC links are inactive or deleted")
                break
            else:
                print("Some VPC links are still active:")
                for vpc_link_id, status in vpc_link_statuses:
                    print(f"  - {vpc_link_id}: {status}")
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry += 1

        if retry > max_retries:
            print("Some VPC links may still be active. Please check manually")
    print()

# TODO: This still needs to be tested.
def delete_rest_api(arn, region):
    '''
    Handles REST APIs. Checks for any associated VPC links and optionally deletes them.
    If VPC links exist and are deleted, the function waits for them to become fully deleted before proceeding.
    '''
    client = boto3.client('apigateway', region_name=region)
    api_id = arn.split('/')[-1]
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
                    print(f"Error retrieving integration for {http_method} on resource {resource_id}: {e}")

    # Prompts user to delete VPC links if they exist.
    if vpc_link_ids:
        delete_vpc_links = 'n'
        delete_vpc_links = input(f"Found {len(vpc_link_ids)} VPC link(s) associated with REST API {arn}. Delete them? (y/n): ").strip().lower()
        if delete_vpc_links != 'y':
            print("VPC links will not be deleted.")
        else:
            # Deletes VPC links if user confirms
            for vpc_link_id in vpc_link_ids:
                try:
                    response = client.delete_vpc_link(VpcLinkId=vpc_link_id)
                    status_code = response['ResponseMetadata']['HTTPStatusCode']
                    if 200 <= status_code < 300:
                        print(f"VPC link {vpc_link_id} was successfully deleted")
                    else:
                        print(f"VPC link {vpc_link_id} was not successfully deleted")
                    print(json.dumps(response, indent=4, default=str))
                except botocore.exceptions.ClientError as e:
                    print(f"Error deleting VPC link {vpc_link_id}: {e}")

    # Deletes the REST API
    try:
        response = client.delete_rest_api(ApiId=api_id)
        status_code = response['ResponseMetadata']['HTTPStatusCode']
        if 200 <= status_code < 300:
            print(f"HTTP API {arn} was successfully deleted")
        else:
            print(f"HTTP API {arn} was not successfully deleted")
        print(json.dumps(response, indent=4, default=str))
    except botocore.exceptions.ClientError as e:
        print(f"Failed to delete API {arn}: {e}")

    # Wait for VPC links to be deleted or reach a non-active state
    if vpc_link_ids and delete_vpc_links == 'y':
        print("Checking status(es) of VPC link(s) to avoid dependency violations...\n")
        max_retries = 5
        retry_delay = 5
        retry = 0

        while retry <= max_retries:
            still_exists = []

            for vpc_link_id in vpc_link_ids:
                try:
                    response = client.get_vpc_link(vpcLinkId=vpc_link_id)
                    status = response.get('status', '')
                    print(f"VPC link {vpc_link_id} status: {status}")
                    still_exists.append((vpc_link_id, status))
                except botocore.exceptions.ClientError as e:
                    if e.response['Error']['Code'] == 'NotFoundException':
                        print(f"VPC link {vpc_link_id} has been fully deleted.")
                        continue
                    else:
                        print(f"Error checking status for VPC link {vpc_link_id}: {e}")
                        still_exists.append((vpc_link_id, 'ERROR'))

            if not still_exists:
                print("All VPC links have been fully deleted.")
                break
            else:
                print("Waiting for VPC links to be fully deleted...")
                retry += 1
                time.sleep(retry_delay)

        if retry >= max_retries:
            print("Some VPC links may still exist. Please check manually.")


####################### AutoScaling Service #########################

def delete_autoscaling_group(arn, region):
    print(f"Deleting autoscaling group {arn}...\n")
    client = boto3.client('autoscaling', region_name=region)
    asg_name = arn.split('/')[-1]
    response = client.delete_auto_scaling_group(AutoScalingGroupName=asg_name, ForceDelete=True)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"Autoscaling group {arn} was successfully deleted")
    else:
        print(f"Autoscaling group {arn} was not successfully deleted")
    print(json.dumps(response, indent=4, default=str))
    print()

####################### CloudFront Service ##########################

def delete_cloudfront_distribution(arn):
    client = boto3.client('cloudfront')
    distribution_id = arn.split('/')[-1]
    print(f"Deleting CloudFront distribution {distribution_id}...\n")

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
            print(f"CloudFront distribution {arn} was successfully deleted")
        else:
            print(f"CloudFront distribution {arn} was not successfully deleted")
        print(json.dumps(response, indent=4, default=str))
    except client.exceptions.DistributionNotDisabled:
        print(f"Distribution {distribution_id} is not yet fully disabled. Please try again in a few minutes.")
    except Exception as e:
        print(f"Error deleting distribution {distribution_id}: {str(e)}")

    print()


def disable_cloudfront_distribution(arn):
    client = boto3.client('cloudfront')
    distribution_id = arn.split('/')[-1]
    print(f"Disabling CloudFront distribution {distribution_id}...\n")
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
        print(f"Disabling CloudFront distribution {distribution_id}. Will come back to delete...")
        client.update_distribution(
            Id=distribution_id,
            DistributionConfig=config,
            IfMatch=etag
        )
        retry = True

    else:
        print(f"CloudFront distribution {distribution_id} is already disabled. Trying to delete...")
        try:
            response = client.delete_distribution(
                Id=distribution_id,
                IfMatch=etag
            )
            if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
                print(f"CloudFront distribution {arn} was successfully deleted")
                retry = False
            else:
                print(f"CloudFront distribution {arn} was not successfully deleted")
            print(json.dumps(response, indent=4, default=str))
        except client.exceptions.DistributionNotDisabled:
            print(f"CloudFront distribution {distribution_id} is not yet fully disabled. Will retry later...")
            retry = True
        except Exception as e:
            print(f"Error deleting CloudFront distribution {distribution_id}: {str(e)}")
            retry = True

    print()
    return retry


def wait_for_distribution_disabled(arn):
    client = boto3.client('cloudfront')
    distribution_id = arn.split('/')[-1]
    print(f"Waiting for CloudFront distribution {distribution_id} to be disabled...")
    waiter = client.get_waiter('distribution_deployed')
    waiter.wait(
        Id=distribution_id,
        WaiterConfig={
            'Delay': 30,
            'MaxAttempts': 20
        }
    )
    print(f"CloudFront distribution {distribution_id} disabled.")
    print()

######################## DynamoDB Service ###########################

def delete_dynamodb_table(arn, region):
    """
    Deletes a DynamoDB table. If the table has deletion protection or items,
    the user will be prompted before proceeding.
    """
    print(f"Deleting DynamoDB table {arn}...\n")
    client = boto3.client('dynamodb', region_name=region)
    table_name = arn.split('/')[-1]

    # Check for deletion protection
    try:
        table_info = client.describe_table(TableName=table_name)['Table']
    except client.exceptions.ResourceNotFoundException:
        print(f"Table {table_name} does not exist. It's possible that it has been deleted already.")
        return

    deletion_protection = table_info.get('DeletionProtectionEnabled', False)
    if deletion_protection:
        disable_protection = input(
            f"\n**** WARNING ****:Table {table_name} has deletion protection enabled. Disable it? (yes/no): "
        ).strip().lower()
        if disable_protection != 'yes':
            print(f"Skipping deletion of DynamoDB table {table_name}")
            return

        # Disable deletion protection
        response = client.update_table(
            TableName=table_name,
            DeletionProtectionEnabled=False
        )
        print(f"Deletion protection disabled for table {table_name}")
        print(json.dumps(response, indent=4, default=str))

    # Check if table has items
    response = client.scan(TableName=table_name, Limit=1)
    if len(response.get('Items', [])) > 0:
        confirm = input(
            f"\n**** WARNING ****: Table {table_name} is not empty. Delete all items and the table? (yes/no): "
        ).strip().lower()
        if confirm != 'yes':
            print(f"Skipping deletion of DynamoDB table {table_name}")
            return

    # Delete the table
    response = client.delete_table(TableName=table_name)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"DynamoDB table {table_name} was successfully deleted")
    else:
        print(f"DynamoDB table {table_name} was not successfully deleted")
    print(json.dumps(response, indent=4, default=str))
    print()

########################### EC2 Service #############################

def deregister_ami(arn, region):
    print(f"Deregistering AMI {arn}...\n")
    client = boto3.client('ec2', region_name=region)
    response = client.deregister_image(ImageId=arn)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"AMI {arn} was successfully deregistered")
    else:
        print(f"AMI {arn} was not successfully deregistered")
    print(json.dumps(response, indent=4, default=str))
    print()


def delete_ec2_instance(arn, region):
    client = boto3.client('ec2', region_name=region)
    instance_id = arn.split('/')[-1]
    print(f"Terminating EC2 instance {instance_id}...\n")

    try:
        response = client.describe_instances(InstanceIds=[instance_id])
    except botocore.exceptions.ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        if error_code == 'InvalidInstanceID.NotFound':
            print(f"EC2 instance {instance_id} not found. It may have already been terminated.\n")
            return
        else:
            print(f"Error describing EC2 instance {instance_id}: {e}")
            raise
            print()

    if not response['Reservations']:
        print(f"EC2 instance {instance_id} not found. It may have already been terminated.\n")
        return

    instance_status = response['Reservations'][0]['Instances'][0]['State']['Name']

    if instance_status in ['terminated', 'shutting-down']:
        print(f"Current status of EC2 instance {instance_id} is: {instance_status}. Skipping...\n")
        return

    response = client.terminate_instances(InstanceIds=[instance_id])
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"EC2 instance {instance_id} was successfully terminated.")
    else:
        print(f"EC2 instance {instance_id} was not successfully terminated.")
    print(json.dumps(response, indent=4, default=str))

    print()


def release_eip(arn, region):
    print(f"Releasing Elastic IP {arn}...\n")
    client = boto3.client('ec2', region_name=region)
    allocation_id = arn.split('/')[-1]
    response = client.release_address(AllocationId=allocation_id)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"Elastic IP {allocation_id} was successfully released")
    else:
        print(f"Elastic IP {allocation_id} was not successfully released")
    print(json.dumps(response, indent=4, default=str))
    print()


def delete_internet_gateway(arn, region):
    client = boto3.client('ec2', region_name=region)
    gateway_id = arn.split('/')[-1]
    print(f"Deleting Internet Gateway {gateway_id}...\n")

    # Detach Internet Gateway if it is attached to a VPC
    print("Checking for VPC attachments...")
    try:
        response = client.describe_internet_gateways(InternetGatewayIds=[gateway_id])
        attachments = response.get('InternetGateways', [])[0].get('Attachments', [])

        for attachment in attachments:
            vpc_id = attachment.get('VpcId')
            if vpc_id:
                client.detach_internet_gateway(InternetGatewayId=gateway_id, VpcId=vpc_id)
                print(f"Internet Gateway {gateway_id} was successfully detached from VPC {vpc_id}")

    except botocore.exceptions.ClientError as e:
        print(f"Failed to detach Internet Gateway {gateway_id}, error: {str(e)}")
        return

    print()

    # Delete Internet Gateway after it has been detached
    print("Proceeding with deletion...")
    try:
        response = client.delete_internet_gateway(InternetGatewayId=gateway_id)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            print(f"Internet gateway {gateway_id} was successfully deleted")
        else:
            print(f"Internet gateway {gateway_id} was not successfully deleted")
        print(json.dumps(response, indent=4, default=str))

    except botocore.exceptions.ClientError as e:
        print(f"Failed to delete {gateway_id}: {str(e)}")

    print()


def delete_nat_gateway(arn, region):
    client = boto3.client('ec2', region_name=region)
    nat_gateway_id = arn.split('/')[-1]
    print(f"Deleting Nat Gateway {nat_gateway_id}...\n")
    deleted = client.describe_nat_gateways(NatGatewayIds=[nat_gateway_id])['NatGateways'][0]['State']
    if deleted == 'deleted' or deleted == 'deleting':
        print(f"Nat gateway {nat_gateway_id} was already deleted")
        return
    try:
        response = client.delete_nat_gateway(NatGatewayId=nat_gateway_id)
        print(f"Nat gateway {nat_gateway_id} deletion initiated")
        print("Waiting for NAT Gateway to complete deletion process...")
        nat_deleted = client.get_waiter('nat_gateway_deleted')
        nat_deleted.wait(
            NatGatewayIds=[nat_gateway_id],
            WaiterConfig={
                'Delay': 10,
                'MaxAttempts': 12
            }
        )
        print(f"Nat gateway {nat_gateway_id} has been fully deleted")
        print(json.dumps(response, indent=4, default=str))
    except Exception as e:
        print(f"Nat gateway {nat_gateway_id} was not fully deleted: {e}")
        return

    print()


def delete_route_table(arn, region):
    client = boto3.client('ec2', region_name=region)
    route_table_id = arn.split('/')[-1]
    print(f"Deleting route table {route_table_id}...\n")

    response = client.delete_route_table(RouteTableId=route_table_id)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"Route table {route_table_id} was successfully deleted")
    else:
        print(f"Route table {route_table_id} was not successfully deleted")
    print(json.dumps(response, indent=4, default=str))

    print()


def delete_snapshot(arn, region):
    print(f"Deleting snapshot {arn}...\n")
    client = boto3.client('ec2', region_name=region)
    response = client.delete_snapshot(SnapshotId=arn)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"Snapshot {arn} was successfully deleted")
    else:
        print(f"Snapshot {arn} was not successfully deleted")
    print(json.dumps(response, indent=4, default=str))

    print()


# TODO: Add a check for hanging ENIs
def delete_subnet(arn, region):
    client = boto3.client('ec2', region_name=region)
    subnet_id = arn.split('/')[-1]

    print(f"Deleting subnet {subnet_id}...\n")

    # Find any route tables associated with the subnet and detach them
    print("Looking for associated route tables...\n")
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
        print(f"Route tables associated with subnet {subnet_id}:\n")
        for rt in associations:
            print(rt['route_table_id'])
        print(f"\nDisassociating route tables from subnet {subnet_id}...")
        for rt in associations:
            response = client.disassociate_route_table(AssociationId=rt['association_id'])
            if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
                print(f"Route table {rt['route_table_id']} was successfully disassociated from subnet {subnet_id}")
            else:
                print(f"Route table {rt['route_table_id']} was not successfully disassociated from subnet {subnet_id}")
            print(json.dumps(response, indent=4, default=str))

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
    #         print(json.dumps(response, indent=4, default=str))


    # Delete subnet
    print("Initiating subnet deletion...")
    response = client.delete_subnet(SubnetId=subnet_id)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"Subnet {subnet_id} was successfully deleted")
    else:
        print(f"Subnet {subnet_id} was not successfully deleted")
    print(json.dumps(response, indent=4, default=str))

    print()


def delete_vpc_endpoint(arn, region):
    client = boto3.client('ec2', region_name=region)
    endpoint_id = arn.split('/')[-1]
    print(f"Deleting VPC endpoint {endpoint_id}...\n")
    try:
        response = client.delete_vpc_endpoints(VpcEndpointIds=[endpoint_id])

        # Check for any errors in the response
        if 'Unsuccessful' in response:
            for error in response['Unsuccessful']:
                # Check if VPC endpoint was already deleted
                if 'Error' in error and error['Error']['Code'] == 'InvalidVpcEndpoint.NotFound':
                    print(f"VPC endpoint {endpoint_id} was already deleted.\n")
                    return None

        # If deletion is successful
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            print(f"VPC endpoint {endpoint_id} was successfully deleted\n")
        else:
            print(f"VPC endpoint {endpoint_id} was not successfully delete\n")

        # Print the full response for debugging
        print(json.dumps(response, indent=4, default=str))
        print()

    except botocore.exceptions.ClientError as e:
        print(f"Failed to delete VPC endpoint {endpoint_id}: {str(e)}")
        print()
        return None


def delete_vpc(arn, region):
    client = boto3.client('ec2', region_name=region)
    vpc_id = arn.split('/')[-1]
    print(f"Deleting VPC {vpc_id}...\n")
    print((f"Checking VPC {vpc_id} for security groups...\n"))
    response = client.describe_security_groups(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    security_groups = response['SecurityGroups']
    for sg in security_groups:
        if sg['GroupName'] == 'default':
            continue
        sg_id = sg['GroupId']
        print(f"Deleting security group {sg_id}...")
        response = client.delete_security_group(GroupId=sg_id)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            print(f"Security group {sg_id} was successfully deleted")
        else:
            print(f"Security group {sg_id} was not successfully deleted")
        print(json.dumps(response, indent=4, default=str))\

    print()

    response = client.delete_vpc(VpcId=vpc_id)
    print("Deleting VPC...")
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"VPC {vpc_id} was successfully deleted")
    else:
        print(f"VPC {vpc_id} was not successfully deleted")
    print(json.dumps(response, indent=4, default=str))

    print()


########################## ELBv2 Service ############################

def delete_elastic_load_balancer(arn, region):
    '''
    Deletes ELB as well as any listeners and target groups.
    Handles all types of ELBs besides classic.
    '''
    print(f"Deleting ELB {arn}...\n")
    client = boto3.client('elbv2', region_name=region)

    print("Checking ELB for listeners and target groups...")
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
        print("The following target groups are used by other ELBs and will not be deleted:\n")
        for tg in tgs_attached_to_other_elbs:
            print(tg)
        print(f"ELB {arn} cannot be deleted at this time. Exiting...\n")
        return

    # Confirm deletion of listeners and target groups
    print(f"Proceeding with deleting ELB {arn} will also delete the following listeners and target groups:\n")
    print("    Listeners:")
    for listener in listener_arns:
        print(f"      {listener}")
    print("\n    Target groups:")
    for tg in target_group_arns:
        print(f"      {tg}")
    print()
    delete_tgs_and_listeners = input("Proceed? (y/n): ").strip().lower()

    if delete_tgs_and_listeners != 'y':
        print("Skipping ELB deletion...")
        return

    # Delete listeners
    print("Deleting target groups and listeners...")
    for listener in listener_arns:
        response = client.delete_listener(ListenerArn=listener)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            print(f"Listener {listener} was successfully deleted")
        else:
            print(f"Listener {listener} was not successfully deleted")
        print(json.dumps(response, indent=4, default=str))

        print()

    # Delete target groups
    for tg in target_group_arns:
        response = client.delete_target_group(TargetGroupArn=tg)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            print(f"Target group {tg} was successfully deleted")
        else:
            print(f"Target group {tg} was not successfully deleted")
        print(json.dumps(response, indent=4, default=str))

        print()

    # Delete load balancer
    print("Initiating ELB deletion...")
    response = client.delete_load_balancer(LoadBalancerArn=arn)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"Deletion of load balancer {arn} was successfully initiated")
    else:
        print(f"Deletion of load balancer {arn} was not successfully initiated")
    print(json.dumps(response, indent=4, default=str))

    # Check to make sure load balancer is fully deleted
    print(f"\nWaiting for ELB {arn} to be fully deleted...")
    load_balancer_deleted = client.get_waiter('load_balancers_deleted')
    try:
        load_balancer_deleted.wait(
            LoadBalancerArns=[arn],
            WaiterConfig={'Delay': 10, 'MaxAttempts': 12}
        )
        print(f"Load balancer {arn} has been fully deleted")
    except botocore.exceptions.WaiterError as e:
        print(f"Load balancer {arn} has not been fully deleted: {e}")

    print()


def delete_listener(arn, region):
    client = boto3.client('elbv2', region_name=region)
    try:
        print(f"Deleting listener {arn}...\n")
        response = client.delete_listener(ListenerArn=arn)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            print(f"Listener {arn} was successfully deleted")
        else:
            print(f"Listener {arn} was not successfully deleted")
        print(json.dumps(response, indent=4, default=str))

    except client.exceptions.ListenerNotFoundException:
        print(f"Listener {arn} was not found and may have already been deleted")

    print()


def delete_target_group(arn, region):
    client = boto3.client('elbv2', region_name=region)
    try:
        print(f"Deleting target group {arn}...\n")
        response = client.delete_target_group(TargetGroupArn=arn)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            print(f"Target group {arn} was successfully deleted")
        else:
            print(f"Target group {arn} was not successfully deleted")
        print(json.dumps(response, indent=4, default=str))

    except client.exceptions.TargetGroupNotFoundException:
        print(f"Target group {arn} was not found and may have already been deleted")

    print()

########################### IAM Service #############################

######################### Lambda Service ############################

def delete_lambda_function(arn, region):
    print(f"Deleting Lambda function {arn}...\n")
    client = boto3.client('lambda', region_name=region)
    response = client.delete_function(FunctionName=arn)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"Lambda function {arn} was successfully deleted")
    else:
        print(f"Lambda function {arn} was not successfully deleted")
    print(json.dumps(response, indent=4, default=str))

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
            confirm = input(f"**** WARNING ****: S3 bucket '{bucket_name}' is not empty. Are you sure you want to delete all contents and the bucket? [yes/no]: ").strip().lower()
            if confirm != 'yes':
                print(f"Skipping deletion of bucket '{bucket_name}'.")
                return

            print(f"Emptying bucket '{bucket_name}'...")

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
                            print(f"One or more objects in {bucket_name} encountered errors during the deletion process:")
                            print(json.dumps(errors, indent=4, default=str))
                            print("Bucket cannot be deleted at this time. Exiting...")
                            print()
                            return

            else:
                paginator = client.get_paginator('list_objects_v2')
                for page in paginator.paginate(Bucket=bucket_name):
                    objects_to_delete = [{'Key': obj['Key']} for obj in page.get('Contents', [])]
                    if objects_to_delete:
                        client.delete_objects(Bucket=bucket_name, Delete={'Objects': objects_to_delete})

        # Delete the bucket
        print(f"Deleting bucket '{bucket_name}'...")
        response = client.delete_bucket(Bucket=bucket_name)
        print(f"S3 bucket '{bucket_name}' successfully deleted.")
        print(json.dumps(response, indent=4, default=str))

    except client.exceptions.NoSuchBucket:
        print(f"Bucket '{bucket_name}' does not exist.")
    except Exception as e:
        print(f"Error deleting S3 bucket '{bucket_name}': {e}")

########################## SQS Service ##############################

def delete_sqs_queue(arn, region):
    print(f"Deleting SQS queue {arn}...\n")
    client = boto3.client('sqs', region_name=region)
    queue_name = arn.split(':')[-1]
    queue_url = client.get_queue_url(QueueName=queue_name)['QueueUrl']
    response = client.delete_queue(QueueUrl=queue_url)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"SQS queue {arn} was successfully deleted")
    else:
        print(f"SQS queue {arn} was not successfully deleted")
    print(json.dumps(response, indent=4, default=str))

    print()

###################################################################
# Delete function mappings
###################################################################

DELETE_FUNCTIONS = {
    'apigateway': {
        'restapi': delete_rest_api
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
        'topic': lambda resource: print("deleting topic"),  # delete_topic(resource['arn'])
    },
    'sqs': {
        'queue': delete_sqs_queue
    }
}

