'''
Contains the delete functions as well as the DELETE_FUNCTIONS dictionary, which maps resource and service
to the appropriate individual delete function.
'''

import json
import botocore.exceptions
import boto3

#######################################################################
# Individual Deletion Functions
#######################################################################

######################### API GW Services ###########################

def delete_http_api(arn):
    client = boto3.client('apigatewayv2')
    api_id = arn.split('/')[-1]
    response = client.delete_api(ApiId=api_id)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"HTTP API {arn} was successfully deleted")
    else:
        print(f"HTTP API {arn} was not successfully deleted")

####################### AutoScaling Service #########################

def delete_autoscaling_group(arn):
    client = boto3.client('autoscaling')
    asg_name = arn.split('/')[-1]
    response = client.delete_auto_scaling_group(AutoScalingGroupName=asg_name, ForceDelete=True)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"Autoscaling group {arn} was successfully deleted")
    else:
        print(f"Autoscaling group {arn} was not successfully deleted")
    print(json.dumps(response, indent=4, default=str))

########################### EC2 Service #############################

def delete_ec2_instance(arn):
    client = boto3.client('ec2')
    instance_id = arn.split('/')[-1]
    instance_status = client.describe_instances(InstanceIds=[instance_id])['Reservations'][0]['Instances'][0]['State']['Name']

    if instance_status in ['terminated', 'shutting-down']:
        print(f"Current status of EC@ instance {instance_id} is: {instance_status}. Skipping")
        return
    else:
        response = client.terminate_instances(InstanceIds=[instance_id])
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            print(f"EC2 instance {instance_id} was successfully terminated")
        else:
            print(f"EC2 instance {instance_id} was not successfully terminated")
        print(json.dumps(response, indent=4, default=str))


def release_eip(arn):
    client = boto3.client('ec2')
    allocation_id = arn.split('/')[-1]
    response = client.release_address(AllocationId=allocation_id)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"Elastic IP {allocation_id} was successfully released")
    else:
        print(f"Elastic IP {allocation_id} was not successfully released")
    print(json.dumps(response, indent=4, default=str))


def delete_internet_gateway(arn):
    client = boto3.client('ec2')
    gateway_id = arn.split('/')[-1]

    # Detach Internet Gateway if it is attached to a VPC
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

    # Delete Internet Gateway after it has been detached
    try:
        response = client.delete_internet_gateway(InternetGatewayId=gateway_id)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            print(f"Internet gateway {gateway_id} was successfully deleted")
        else:
            print(f"Internet gateway {gateway_id} was not successfully deleted")
        print(json.dumps(response, indent=4, default=str))

    except botocore.exceptions.ClientError as e:
        print(f"Failed to delete {gateway_id}: {str(e)}")


def delete_nat_gateway(arn):
    client = boto3.client('ec2')
    nat_gateway_id = arn.split('/')[-1]
    deleted = client.describe_nat_gateways(NatGatewayIds=[nat_gateway_id])['NatGateways'][0]['State']
    if deleted == 'deleted' or deleted == 'deleting':
        print(f"Nat gateway {nat_gateway_id} was already deleted")
        return
    try:
        client.delete_nat_gateway(NatGatewayId=nat_gateway_id)
        print(f"Nat gateway {nat_gateway_id} deletion initiated")
        print("Waiting for NAT Gateway to complete deletion process...")
        nat_deleted= client.get_waiter('nat_gateway_deleted')
        nat_deleted.wait(
            NatGatewayIds=[nat_gateway_id],
            WaiterConfig={
                'Delay': 10,
                'MaxAttempts': 12
            }
        )
        print(f"Nat gateway {nat_gateway_id} has been fully deleted")
    except Exception as e:
        print(f"Nat gateway {nat_gateway_id} was not fully deleted: {e}")
        return


def delete_route_table(arn):
    client = boto3.client('ec2')
    route_table_id = arn.split('/')[-1]
    response = client.delete_route_table(RouteTableId=route_table_id)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"Route table {route_table_id} was successfully deleted")
    else:
        print(f"Route table {route_table_id} was not successfully deleted")
    print(json.dumps(response, indent=4, default=str))


def delete_subnet(arn):
    client = boto3.client('ec2')
    subnet_id = arn.split('/')[-1]
    response = client.delete_subnet(SubnetId=subnet_id)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"Subnet {subnet_id} was successfully deleted")
    else:
        print(f"Subnet {subnet_id} was not successfully deleted")
    print(json.dumps(response, indent=4, default=str))


def delete_vpc_endpoint(arn):
    client = boto3.client('ec2')
    endpoint_id = arn.split('/')[-1]
    try:
        response = client.delete_vpc_endpoints(VpcEndpointIds=[endpoint_id])

        # Check for any errors in the response
        if 'Unsuccessful' in response:
            for error in response['Unsuccessful']:
                # Check if VPC endpoint was already deleted
                if 'Error' in error and error['Error']['Code'] == 'InvalidVpcEndpoint.NotFound':
                    print(f"VPC endpoint {endpoint_id} was already deleted.")
                    return None

        # If deletion is successful
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            print(f"VPC endpoint {endpoint_id} was successfully deleted")
        else:
            print(f"VPC endpoint {endpoint_id} was not successfully deleted")

        # Print the full response for debugging
        print(json.dumps(response, indent=4, default=str))

    except botocore.exceptions.ClientError as e:
        print(f"Failed to delete VPC endpoint {endpoint_id}: {str(e)}")
        return None


def delete_vpc(arn):
    client = boto3.client('ec2')
    vpc_id = arn.split('/')[-1]
    response = client.delete_vpc(VpcId=vpc_id)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"VPC {vpc_id} was successfully deleted")
    else:
        print(f"VPC {vpc_id} was not successfully deleted")
    print(json.dumps(response, indent=4, default=str))


########################## ELBv2 Service ############################

def delete_elastic_load_balancer(arn):
    '''
    Deletes ELB as well as any listeners and target groups.
    '''
    client = boto3.client('elbv2')

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

    # Delete listeners - eventually needs to be modified to handle multiple listeners
    for listener in listener_arns:
        response = client.delete_listener(ListenerArn=listener)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            print(f"Listener {listener} was successfully deleted")
        else:
            print(f"Listener {listener} was not successfully deleted")
        print(json.dumps(response, indent=4, default=str))

    # Delete target group - eventually needs to be modified to handle multiple target groups
    for tg in target_group_arns:
        response = client.delete_target_group(TargetGroupArn=tg)
        if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
            print(f"Target group {tg} was successfully deleted")
        else:
            print(f"Target group {tg} was not successfully deleted")
        print(json.dumps(response, indent=4, default=str))

    # Delete load balancer
    response = client.delete_load_balancer(LoadBalancerArn=arn)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"Load balancer {arn} was successfully deleted")
    else:
        print(f"Load balancer {arn} was not successfully deleted")
    print(json.dumps(response, indent=4, default=str))

######################### Lambda Service ############################

def delete_lambda_function(arn):
    client = boto3.client('lambda')
    response = client.delete_function(FunctionName=arn)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"Lambda function {arn} was successfully deleted")
    else:
        print(f"Lambda function {arn} was not successfully deleted")
    print(json.dumps(response, indent=4, default=str))

########################## SQS Service ##############################

def delete_sqs_queue(arn):
    client = boto3.client('sqs')
    queue_name = arn.split(':')[-1]
    queue_url = client.get_queue_url(QueueName=queue_name)['QueueUrl']
    response = client.delete_queue(QueueUrl=queue_url)
    if 200 <= response['ResponseMetadata']['HTTPStatusCode'] < 300:
        print(f"SQS queue {arn} was successfully deleted")
    else:
        print(f"SQS queue {arn} was not successfully deleted")
    print(json.dumps(response, indent=4, default=str))

###################################################################
# Delete function mappings
###################################################################

DELETE_FUNCTIONS = {
    'apigateway': {
        'restapi': lambda resource: print("deleting rest api"),  # delete_rest_api(resource['arn'])
    },
    'apigatewayv2': {
        'api': delete_http_api
    },
    'autoscaling': {
        'autoscalinggroup': delete_autoscaling_group
    },
    'certificatemanager': {
        'certificate': lambda resource: print("deleting certificate"),  # delete_certificate(resource['arn'])
    },
    'cloudfront': {
        'distribution': lambda resource: print("deleting distribution"),  # delete_distribution(resource['arn'])
    },
    'dynamodb': {
        'table': lambda resource: print("deleting table"),  # delete_table(resource['arn'])
    },
    'ec2': {
        'eip': release_eip,
        'instance': delete_ec2_instance,
        'internetgateway': delete_internet_gateway,
        'natgateway': delete_nat_gateway,  # delete_nat_gateway(resource['arn'])
        'route': lambda resource: print("deleting route"),  # delete_route(resource['arn'])
        'routetable': delete_route_table,
        'security_group': lambda resource: print("deleting security group"),  # delete_security_group(resource['arn'])
        'subnet': delete_subnet,
        'transitgatewayattachment': lambda resource: print("deleting transit gateway attachment"),  # delete_transit_gateway_vpc_attachment(resource['arn'])
        'vpc': delete_vpc,
        'vpcendpoint': delete_vpc_endpoint,
        'vpcpeering': lambda resource: print("deleting vpc peering"),  # delete_vpc_peering_connection(resource['arn'])
    },
    'elasticloadbalancing': {
        'loadbalancer': lambda resource: print("deleting load balancer"),  # delete_load_balancer(resource['arn'])
    },
    'elasticloadbalancingv2': {
        'loadbalancer': delete_elastic_load_balancer
    },
    'iam': {
        'policy': lambda resource: print("deleting policy"),  # delete_policy(resource['arn'])
        'role': lambda resource: print("deleting role"),  # delete_role(resource['arn'])
    },
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
        'bucket': lambda resource: print("deleting bucket"),  # delete_bucket(resource['XXX'])
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

