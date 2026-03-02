import json

import boto3

from awsweepbytag import text_formatting as tf


def subnet_dependency_checker(subnet_arn: str, region: str) -> tuple[list[dict], bool]:
    """
    Checks for subnet dependencies and prompts for deletion confirmation if Lambda functions are found.

    1. Checks for any route tables associated with subnet and disassociates them
    2. Checks for NAT Gateways, EC2 instances, and Lambda functions in the subnet
    3. Prompts user for confirmation if Lambda functions are found
    4. Returns list of dependencies that need to be deleted and whether to skip subnet deletion

    Args:
        subnet_arn (str): The ARN of the subnet to check for dependencies
        region (str): The region the subnet is in

    Returns:
        tuple[list[dict], bool]: (list of dependencies to delete, whether to skip subnet deletion)
            - dependencies: List of resource dictionaries that need to be deleted
            - skip: True if subnet deletion should be skipped, False otherwise
    """
    subnet_id = subnet_arn.split("/")[-1]
    account_id = subnet_arn.split(":")[4]

    client = boto3.client("ec2", region_name=region)
    tf.subheader_print(f"Checking for resources attached to subnet '{subnet_id}'...")

    # Find any route tables associated with the subnet and disassociate them
    # This is a prerequisite for subnet deletion, not a resource deletion
    tf.indent_print("Looking for associated route tables...\n")
    route_tables = client.describe_route_tables(Filters=[{"Name": "association.subnet-id", "Values": [subnet_id]}])["RouteTables"]
    associations = [
        {
            "route_table_id": rt["RouteTableId"],
            "association_id": assoc["RouteTableAssociationId"],
        }
        for rt in route_tables
        for assoc in rt.get("Associations", [])
        if assoc.get("SubnetId") == subnet_id
    ]

    # Disassociate route tables from subnet if they are associated
    if associations:
        tf.indent_print(f"Route tables associated with subnet '{subnet_id}':\n")
        for rt in associations:
            tf.indent_print(rt["route_table_id"], indent=6)
        print()
        tf.indent_print(f"Disassociating route tables from subnet '{subnet_id}'...\n")
        for rt in associations:
            response = client.disassociate_route_table(AssociationId=rt["association_id"])
            if 200 <= response["ResponseMetadata"]["HTTPStatusCode"] < 300:
                tf.success_print(f"Route table {rt['route_table_id']} was successfully disassociated from subnet '{subnet_id}'")
            else:
                tf.failure_print(f"Route table {rt['route_table_id']} was not successfully disassociated from subnet '{subnet_id}'")
            tf.response_print(json.dumps(response, indent=4, default=str))

    # Check for resources that need to be deleted before the subnet can be deleted
    tf.indent_print("Checking for NAT Gateways, EC2 instances, and Lambda functions...\n")

    lambda_client = boto3.client("lambda", region_name=region)

    subnet_resource_map = [
        {
            "method": client.describe_nat_gateways,
            "filters": [{"Name": "subnet-id", "Values": [subnet_id]}],
            "response_key": "NatGateways",
            "id_key": "NatGatewayId",
            "resource_type": "nat-gateway",
            "service": "ec2",
        },
        {
            "method": client.describe_instances,
            "filters": [{"Name": "subnet-id", "Values": [subnet_id]}],
            "response_key": "Reservations",
            "id_key": "InstanceId",
            "resource_type": "instance",
            "service": "ec2",
        },
    ]

    dependencies = []
    lambda_dependencies = []

    # Collect all dependencies from the subnet
    for meta in subnet_resource_map:
        response = meta["method"](Filters=meta["filters"])

        # Handle Reservations response structure for EC2 instances
        if meta["response_key"] == "Reservations":
            for reservation in response.get(meta["response_key"], []):
                for instance in reservation.get("Instances", []):
                    resource_id = instance.get(meta["id_key"])
                    if not resource_id:
                        continue
                    resource_type = meta["resource_type"]
                    service = meta["service"]
                    arn = f"arn:aws:{service}:{region}:{account_id}:{resource_type}/{resource_id}"
                    dependencies.append({"resource_type": resource_type.replace("-", ""), "arn": arn, "service": service, "region": region})
        else:
            # Handle standard response structure for NAT Gateways
            for resource in response.get(meta["response_key"], []):
                resource_id = resource.get(meta["id_key"])
                if not resource_id:
                    continue
                resource_type = meta["resource_type"]
                service = meta["service"]
                arn = f"arn:aws:{service}:{region}:{account_id}:{resource_type}/{resource_id}"
                dependencies.append({"resource_type": resource_type.replace("-", ""), "arn": arn, "service": service, "region": region})

    # Check for Lambda functions attached to this subnet
    try:
        lambda_response = lambda_client.list_functions()
        for function in lambda_response.get("Functions", []):
            vpc_config = function.get("VpcConfig", {})
            subnet_ids = vpc_config.get("SubnetIds", [])

            if subnet_id in subnet_ids:
                function_arn = function["FunctionArn"]
                lambda_dependencies.append({"resource_type": "function", "arn": function_arn, "service": "lambda", "region": region})
    except Exception as e:
        tf.failure_print(f"Error checking Lambda functions for subnet '{subnet_id}': {e}")
        # Continue with other dependencies even if Lambda check fails

    # If Lambda functions are found, prompt for confirmation
    if lambda_dependencies:
        tf.subheader_print(f"Found {len(lambda_dependencies)} Lambda function(s) attached to subnet '{subnet_id}':")
        for dep in lambda_dependencies:
            print(json.dumps(dep, indent=4))
        print()
        delete = tf.y_n_prompt("Lambda functions must be deleted before the subnet can be deleted. Continue?")
        print()

        if delete != "y":
            print()
            tf.indent_print(f"Skipping deletion of subnet '{subnet_id}' and its Lambda dependencies...\n")
            return [], True

        # Add Lambda dependencies to the main dependencies list
        dependencies.extend(lambda_dependencies)

    if len(dependencies) == 0:
        tf.indent_print(f"No dependencies found in subnet '{subnet_id}'.\n")
    else:
        tf.indent_print(f"Found {len(dependencies)} resource(s) in subnet '{subnet_id}' that need to be deleted:\n")
        for dep in dependencies:
            tf.indent_print(f"{dep['resource_type']}: {dep['arn']}", indent=6)
        print()

    return dependencies, False



def vpc_dependency_checker(vpc_arn: str, region: str) -> tuple[list[dict], bool]:
    """
    Check a VPC for dependencies and prompts for deletion confirmation.

    1. Checks the VPC for the following dependencies that would prevent VPC deletion:
        - VPC Endpoints
        - Subnets
        - Internet Gateways
        - Route Tables
        - Security Groups (excluding default)
        - Lambda Functions
    2. Prompts user for deletion confirmation
    3. Returns dependencies and whether to skip VPC deletion

    Args:
        vpc_arn (str): The ARN of the VPC to check for dependencies
        region (str): The region the VPC is in

    Returns:
        tuple[list[dict], bool]: (list of dependencies to delete, whether to skip VPC deletion)
            - dependencies: List of resource dictionaries that need to be deleted
            - skip: True if VPC deletion should be skipped, False otherwise
    """
    vpc_id = vpc_arn.split("/")[-1]
    account_id = vpc_arn.split(":")[4]

    tf.subheader_print(f"Checking VPC '{vpc_id}' for attached resources...")

    client = boto3.client("ec2", region_name=region)

    # Check for attached resources that would prevent VPC deletion
    vpc_resource_map = [
        {
            "method": client.describe_vpc_endpoints,
            "filters": [{"Name": "vpc-id", "Values": [vpc_id]}],
            "response_key": "VpcEndpoints",
            "id_key": "VpcEndpointId",
            "resource_type": "vpc-endpoint",
        },
        {
            "method": client.describe_subnets,
            "filters": [{"Name": "vpc-id", "Values": [vpc_id]}],
            "response_key": "Subnets",
            "id_key": "SubnetId",
            "resource_type": "subnet",
        },
        {
            "method": client.describe_internet_gateways,
            "filters": [{"Name": "attachment.vpc-id", "Values": [vpc_id]}],
            "response_key": "InternetGateways",
            "id_key": "InternetGatewayId",
            "resource_type": "internet-gateway",
        },
        {
            "method": client.describe_route_tables,
            "filters": [{"Name": "vpc-id", "Values": [vpc_id]}, {"Name": "association.main", "Values": ["false"]}],
            "response_key": "RouteTables",
            "id_key": "RouteTableId",
            "resource_type": "route-table",
        },
    ]

    dependencies = []

    # Collect attached vpc_endpoints, subnets, internet_gateways, route_tables
    for meta in vpc_resource_map:
        response = meta["method"](Filters=meta["filters"])
        for resource in response.get(meta["response_key"], []):
            resource_id = resource.get(meta["id_key"])
            if not resource_id:
                continue
            resource_type = meta["resource_type"]
            arn = f"arn:aws:ec2:{region}:{account_id}:{resource_type}/{resource_id}"
            dependencies.append({"resource_type": resource_type.replace("-", ""), "arn": arn, "service": "ec2", "region": region})

    # Security groups handled separately since "default" needs to be filtered out
    security_groups = client.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])["SecurityGroups"]
    for sg in security_groups:
        if sg["GroupName"] != "default":
            resource_id = sg["GroupId"]
            arn = f"arn:aws:ec2:{region}:{account_id}:security-group/{resource_id}"
            dependencies.append({"resource_type": "securitygroup", "arn": arn, "service": "ec2", "region": region})

    # Check for Lambda functions attached to this VPC
    lambda_client = boto3.client("lambda", region_name=region)
    try:
        lambda_response = lambda_client.list_functions()
        for function in lambda_response.get("Functions", []):
            vpc_config = function.get("VpcConfig", {})
            function_vpc_id = vpc_config.get("VpcId")

            if function_vpc_id == vpc_id:
                function_arn = function["FunctionArn"]
                dependencies.append({"resource_type": "function", "arn": function_arn, "service": "lambda", "region": region})
    except Exception as e:
        tf.failure_print(f"Error checking Lambda functions for VPC '{vpc_id}': {e}")
        # Continue with other dependencies even if Lambda check fails

    if len(dependencies) == 0:
        tf.indent_print(f"No dependencies found for VPC '{vpc_id}'.\n")
        return [], False

    tf.subheader_print(f"Found the following dependencies attached to VPC '{vpc_id}':")
    for dependency in dependencies:
        print(json.dumps(dependency, indent=4))

    print()
    delete = tf.y_n_prompt("If you continue all dependencies will be deleted as well. Continue?")
    print()

    if delete != "y":
        print()
        tf.indent_print(f"Skipping deletion of VPC '{vpc_id}' and its dependencies...\n")
        return [], True

    return dependencies, False