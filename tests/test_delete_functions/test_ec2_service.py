import json
import logging
import os
from unittest.mock import patch

import boto3
import botocore.exceptions
import pytest
from moto import mock_aws

from awsweepbytag import delete_functions
from awsweepbytag.logger import get_colored_stream_handler

log_level_str = os.getenv("LOG_LEVEL", "WARNING").upper()
log_level = getattr(logging, log_level_str)

logger = logging.getLogger(__name__)
logger.setLevel(log_level)

if not logger.handlers:
    logger.addHandler(get_colored_stream_handler())


################################### Common Exceptions ####################################
def throttling_exception(*args, **kwargs):
    raise botocore.exceptions.ClientError({"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "DeleteLaunchTemplate")


def not_found_exception(*args, **kwargs):
    raise botocore.exceptions.ClientError({"Error": {"Code": "NotFoundException", "Message": "Not found"}}, "DeleteLaunchTemplate")


################################### deregister_ami tests ######################################
@mock_aws
def test_deregister_ami(capsys):
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)

    # Create an instance
    create_response = client.run_instances(ImageId="ami-05f417c208be02d4d", InstanceType="t2.nano", MinCount=1, MaxCount=1)
    instance_id = create_response["Instances"][0]["InstanceId"]

    # Create an AMI
    create_response = client.create_image(Name="test-image", InstanceId=instance_id)
    ami_id = create_response["ImageId"]
    arn = f"arn:aws:ec2:{region}:123456789012:image/{ami_id}"
    logger.debug(f"AMI ARN for test: {arn}")

    # Confirm it exists
    images = client.describe_images()["Images"]
    assert any(i["ImageId"] == ami_id for i in images)

    # Run delete function
    result = delete_functions.deregister_ami(arn, region)
    output = capsys.readouterr().out
    assert f"AMI '{ami_id}' was successfully deregistered" in output
    assert result is None

    # Confirm it was deleted
    images = client.describe_images()["Images"]
    assert not any(i["ImageId"] == ami_id for i in images)


################################### delete_ec2_instance tests ######################################
@mock_aws
def test_delete_ec2_instance(capsys):
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)

    # Create an instance
    create_response = client.run_instances(ImageId="ami-05f417c208be02d4d", InstanceType="t2.nano", MinCount=1, MaxCount=1)
    instance_id = create_response["Instances"][0]["InstanceId"]
    logger.debug(f"Instance ID for test: {instance_id}")
    arn = f"arn:aws:ec2:{region}:123456789012:instance/{instance_id}"

    # Confirm it exists
    instances = client.describe_instances()["Reservations"][0]["Instances"]
    assert any(i["InstanceId"] == instance_id for i in instances)

    # Run delete function
    result = delete_functions.delete_ec2_instance(arn, region)
    output = capsys.readouterr().out
    assert f"EC2 instance '{instance_id}' is shutting down." in output
    assert "TerminatingInstances" in output
    assert '"HTTPStatusCode": 200,' in output
    assert f"Waiting for EC2 instance '{instance_id}' to terminate to avoid dependency violations..." in output
    assert f"EC2 instance '{instance_id}' has been terminated." in output
    assert result is None

    # Confirm state of instance is terminated
    instances = client.describe_instances()["Reservations"][0]["Instances"]
    instance = next(i for i in instances if i["InstanceId"] == instance_id)
    assert instance["State"]["Name"] == "terminated"


@mock_aws
def test_delete_ec2_instance_not_found(capsys):
    # Arrange
    region = "us-east-1"
    instance_id = "i-0b3697156fd669628"
    arn = f"arn:aws:ec2:{region}:123456789012:instance/{instance_id}"

    result = delete_functions.delete_ec2_instance(arn, region)

    # Assert correct message was printed
    output = capsys.readouterr().out
    assert f"Terminating EC2 instance '{instance_id}' in {region}..." in output
    assert f"EC2 instance '{instance_id}' not found. It may have already been terminated." in output
    assert result is None


@mock_aws
@patch("boto3.client")
def test_delete_ec2_instance_state_shutting_down(mock_boto_client, capsys):
    instance_id = "i-0b3697156fd669628"
    instance_status = "shutting-down"
    mock_client = mock_boto_client.return_value
    mock_client.describe_instances.return_value = {
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceId": instance_id,
                        "State": {"Code": 32, "Name": instance_status},
                    }
                ]
            }
        ]
    }

    region = "us-east-1"
    instance_id = "i-0b3697156fd669628"
    arn = f"arn:aws:ec2:{region}:123456789012:instance/{instance_id}"
    result = delete_functions.delete_ec2_instance(arn, region)
    output = capsys.readouterr().out

    assert f"Current status of EC2 instance '{instance_id}' is: '{instance_status}'. Skipping..." in output
    assert f"EC2 instance '{instance_id}' is shutting down." not in output
    assert result is None


@mock_aws
def test_delete_ec2_instance_autoscaling_true(capsys):
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)

    # Create an instance
    create_response = client.run_instances(ImageId="ami-05f417c208be02d4d", InstanceType="t2.nano", MinCount=1, MaxCount=1)
    instance_id = create_response["Instances"][0]["InstanceId"]
    logger.debug(f"Instance ID for test: {instance_id}")
    arn = f"arn:aws:ec2:{region}:123456789012:instance/{instance_id}"

    # Confirm it exists
    instances = client.describe_instances()["Reservations"][0]["Instances"]
    assert any(i["InstanceId"] == instance_id for i in instances)

    # Run delete function
    result = delete_functions.delete_ec2_instance(arn, region, True)
    output = capsys.readouterr().out
    assert f"EC2 instance '{instance_id}' is shutting down." in output
    assert "TerminatingInstances" in output
    assert '"HTTPStatusCode": 200,' in output
    assert result is None

    # These lines should not display if autoscaling = True (If the function is called by delete_autoscaling_group)
    assert f"Waiting for EC2 instance '{instance_id}' to terminate to avoid dependency violations..." not in output
    assert f"EC2 instance '{instance_id}' has been terminated." not in output

    # Confirm state of instance is terminated
    instances = client.describe_instances()["Reservations"][0]["Instances"]
    instance = next(i for i in instances if i["InstanceId"] == instance_id)
    assert instance["State"]["Name"] == "terminated"


################################### release_eip tests ######################################
@mock_aws
def test_release_eip(capsys):
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)

    # Create an EIP
    create_response = client.allocate_address(Domain="vpc")
    eip_id = create_response["AllocationId"]
    arn = f"arn:aws:ec2:{region}:123456789012:eip-allocation/{eip_id}"

    # Confirm it exists
    eips = client.describe_addresses()["Addresses"]
    assert any(e["AllocationId"] == eip_id for e in eips)

    # Run delete function
    result = delete_functions.release_eip(arn, region)
    output = capsys.readouterr().out
    assert f"Elastic IP '{eip_id}' was successfully released" in output
    assert result is None

    # Confirm it was deleted
    eips = client.describe_addresses()["Addresses"]
    assert not any(e["AllocationId"] == eip_id for e in eips)


################################### delete_internet_gateway tests ######################################
@mock_aws
def test_delete_internet_gateway(capsys):
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)

    # Create a VPC
    vpc_response = client.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_response["Vpc"]["VpcId"]
    logger.debug(f"VPC ID for test: {vpc_id}")

    # Create an IGW
    gateway_id = client.create_internet_gateway()["InternetGateway"]["InternetGatewayId"]
    arn = f"arn:aws:ec2:{region}:123456789012:igw/{gateway_id}"
    logger.debug(f"IGW ID for test: {gateway_id}")

    # Attach IGW to VPC
    response = client.attach_internet_gateway(InternetGatewayId=gateway_id, VpcId=vpc_id)
    assert 200 <= response["ResponseMetadata"]["HTTPStatusCode"] < 300

    # Check that IGW exists and is attached to VPC
    response = client.describe_internet_gateways(InternetGatewayIds=[gateway_id])
    igw_attachments = response["InternetGateways"][0]["Attachments"]
    assert any(a["VpcId"] == vpc_id for a in igw_attachments)
    assert "available" in igw_attachments[0]["State"]
    logger.debug(f"IGW attachments for test: {igw_attachments}")

    result = delete_functions.delete_internet_gateway(arn, region)
    output = capsys.readouterr().out

    # Check expected results from delete_internet_gateway function
    assert result is None
    assert f"Deleting Internet Gateway '{gateway_id}' in {region}..." in output
    assert "Checking for VPC attachments..." in output
    assert f"Internet Gateway '{gateway_id}' was successfully detached from VPC {vpc_id}" in output
    assert "Proceeding with deletion..." in output
    assert f"Internet gateway '{gateway_id}' was successfully deleted" in output

    # Check that IGW is deleted
    response = client.describe_internet_gateways()
    internet_gateways = response.get("InternetGateways", [])
    gateway_ids = [igw["InternetGatewayId"] for igw in internet_gateways]
    assert gateway_id not in gateway_ids


################################### delete_launch_template tests ######################################
@mock_aws
def test_delete_launch_template(capsys):
    region = "us-west-2"
    client = boto3.client("ec2", region_name=region)

    # Create a launch template
    create_response = client.create_launch_template(
        LaunchTemplateName="test-template", LaunchTemplateData={"ImageId": "ami-12345678", "InstanceType": "t2.nano"}
    )

    template_id = create_response["LaunchTemplate"]["LaunchTemplateId"]
    arn = f"arn:aws:ec2:{region}:123456789012:launch-template/{template_id}"

    # Confirm it exists
    templates = client.describe_launch_templates()["LaunchTemplates"]
    assert any(t["LaunchTemplateId"] == template_id for t in templates)

    # Run delete function
    result = delete_functions.delete_launch_template(arn, region)
    output = capsys.readouterr().out
    assert f"Launch template '{template_id}' was successfully deleted" in output
    assert result is None
    # print(output)

    # Confirm it was deleted
    templates = client.describe_launch_templates()["LaunchTemplates"]
    assert not any(t["LaunchTemplateId"] == template_id for t in templates)


@mock_aws
def test_delete_launch_template_not_found(capsys):
    # Arrange
    region = "us-east-1"
    template_id = "lt-0abcd1234efgh5678"
    arn = f"arn:aws:ec2:{region}::launch-template/{template_id}"

    # Moto starts with no templates — deletion of this should raise ClientError with code InvalidLaunchTemplateId.NotFound
    # Act
    result = delete_functions.delete_launch_template(arn, region)

    # Assert function returns None
    assert result is None

    # Assert correct message was printed
    output = capsys.readouterr().out
    assert f"Launch template '{template_id}' not found. It may have already been deleted." in output
    assert result is None
    # print(output)


@patch("boto3.client")
def test_delete_launch_template_throttling(mock_boto_client, capsys):
    throttling_exception = botocore.exceptions.ClientError(
        error_response={"Error": {"Code": "ThrottlingException", "Message": "ThrottlingException"}},
        operation_name="DeleteLaunchTemplate",
    )
    # Arrange
    mock_client = mock_boto_client.return_value
    mock_client.delete_launch_template.side_effect = throttling_exception

    region = "us-east-1"
    lt_id = "lt-0123456789abcdef0"
    arn = f"arn:aws:ec2:us-east-1::launch-template/{lt_id}"

    # Act + Assert
    with pytest.raises(botocore.exceptions.ClientError) as exc_info:
        delete_functions.delete_launch_template(arn, region)
    output = capsys.readouterr().out
    assert f"Deleting Launch Template '{lt_id}' in {region}..." in output

    assert "ThrottlingException" in str(exc_info.value)


################################### delete_nat_gateway tests ######################################
@mock_aws
def test_delete_nat_gateway(capsys):
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)

    # Create a VPC
    vpc_response = client.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_response["Vpc"]["VpcId"]
    logger.debug(f"VPC ID for test: {vpc_id}")

    # Create a subnet
    subnet_response = client.create_subnet(VpcId=vpc_id, CidrBlock="10.0.0.0/24")
    subnet_id = subnet_response["Subnet"]["SubnetId"]
    logger.debug(f"Subnet ID for test: {subnet_id}")

    # Create a NAT gateway
    nat_gateway_id = client.create_nat_gateway(SubnetId=subnet_id)["NatGateway"]["NatGatewayId"]
    arn = f"arn:aws:ec2:{region}:123456789012:natgateway/{nat_gateway_id}"
    logger.debug(f"NAT Gateway ID for test: {nat_gateway_id}")

    # Confirm it exists
    nat_gateways = client.describe_nat_gateways()["NatGateways"]
    assert any(n["NatGatewayId"] == nat_gateway_id for n in nat_gateways)

    # Run delete function
    result = delete_functions.delete_nat_gateway(arn, region)
    output = capsys.readouterr().out
    assert f"Deleting Nat Gateway '{nat_gateway_id}' in {region}..." in output
    assert f"Nat gateway '{nat_gateway_id}' deletion initiated" in output
    assert "Waiting for NAT Gateway to complete deletion process..." in output
    assert f"Nat gateway '{nat_gateway_id}' has been fully deleted" in output
    assert result is None


################################### delete_route_table tests ######################################
@mock_aws
def test_delete_route_table(capsys):
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)

    # Create a VPC
    vpc_response = client.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_response["Vpc"]["VpcId"]
    logger.debug(f"VPC ID for test: {vpc_id}")

    # Create a route table
    route_table_id = client.create_route_table(VpcId=vpc_id)["RouteTable"]["RouteTableId"]
    arn = f"arn:aws:ec2:{region}:123456789012:route-table/{route_table_id}"
    logger.debug(f"Route table ID for test: {route_table_id}")

    # Confirm it exists
    route_tables = client.describe_route_tables()["RouteTables"]
    assert any(r["RouteTableId"] == route_table_id for r in route_tables)

    # Run delete function
    result = delete_functions.delete_route_table(arn, region)
    output = capsys.readouterr().out
    assert f"Deleting route table '{route_table_id}' in {region}..." in output
    assert f"Route table '{route_table_id}' was successfully deleted" in output
    assert result is None

    # Confirm deletion
    route_tables = client.describe_route_tables()["RouteTables"]
    assert not any(r["RouteTableId"] == route_table_id for r in route_tables)


################################### delete_security_group tests ######################################
@mock_aws
def test_delete_security_group(capsys):
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)

    # Create a VPC
    vpc_response = client.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_response["Vpc"]["VpcId"]
    logger.debug(f"VPC ID for test: {vpc_id}")

    # Create a security group
    sg_id = client.create_security_group(GroupName="test-group", Description="Test group")["GroupId"]
    arn = f"arn:aws:ec2:{region}:123456789012:security-group/{sg_id}"
    logger.debug(f"Security group ID for test: {sg_id}")

    # Confirm it exists
    groups = client.describe_security_groups()["SecurityGroups"]
    assert any(g["GroupId"] == sg_id for g in groups)

    # Run delete function
    result = delete_functions.delete_security_group(arn, region)
    output = capsys.readouterr().out
    assert f"Deleting security group '{sg_id}' in {region}..." in output
    assert f"Security group '{sg_id}' was successfully deleted" in output
    assert result is None

    # Confirm deletion
    security_groups = client.describe_security_groups()["SecurityGroups"]
    assert not any(g["GroupId"] == sg_id for g in security_groups)


################################### delete_snapshot tests ######################################
@mock_aws
def test_delete_snapshot(capsys):
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)

    # Create a volume
    volume_id = client.create_volume(Size=1, AvailabilityZone=f"{region}a")["VolumeId"]

    # Create a snapshot
    snapshot_id = client.create_snapshot(VolumeId=volume_id)["SnapshotId"]
    arn = f"arn:aws:ec2:{region}:123456789012:snapshot/{snapshot_id}"
    logger.debug(f"Snapshot ID for test: {snapshot_id}")

    # Confirm it exists
    snapshots = client.describe_snapshots(SnapshotIds=[snapshot_id])["Snapshots"]
    assert any(s["SnapshotId"] == snapshot_id for s in snapshots)

    # Run delete function
    result = delete_functions.delete_snapshot(arn, region)
    output = capsys.readouterr().out
    assert f"Deleting snapshot '{snapshot_id}' in {region}..." in output
    assert f"Snapshot '{snapshot_id}' was successfully deleted" in output
    assert result is None

    # Confirm deletion
    response = client.describe_snapshots()
    snapshots = response.get("Snapshots", [])
    snapshot_ids = [s["SnapshotId"] for s in snapshots]
    assert snapshot_id not in snapshot_ids


################################### delete_subnet tests ######################################
@mock_aws
def test_delete_subnet_with_route_table_association(capsys):
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)

    # Create a VPC
    vpc_response = client.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_response["Vpc"]["VpcId"]
    logger.debug(f"VPC ID for test: {vpc_id}")

    # Create a subnet
    subnet_response = client.create_subnet(VpcId=vpc_id, CidrBlock="10.0.0.0/24")
    subnet_id = subnet_response["Subnet"]["SubnetId"]
    arn = f"arn:aws:ec2:{region}:123456789012:subnet/{subnet_id}"
    logger.debug(f"Subnet ID for test: {subnet_id}")

    # Create a route table
    route_table_id = client.create_route_table(VpcId=vpc_id)["RouteTable"]["RouteTableId"]

    # Associate route table with subnet
    client.associate_route_table(RouteTableId=route_table_id, SubnetId=subnet_id)

    # Confirm it exists
    subnets = client.describe_subnets()["Subnets"]
    assert any(s["SubnetId"] == subnet_id for s in subnets)

    # Confirm route table is associated with subnet
    route_tables = client.describe_route_tables()["RouteTables"]
    subnet_route_table_id = next(
        (rt["RouteTableId"] for rt in route_tables for assoc in rt.get("Associations", []) if assoc.get("SubnetId") == subnet_id), None
    )
    assert subnet_route_table_id == route_table_id

    # Run delete function
    result = delete_functions.delete_subnet(arn, region)
    output = capsys.readouterr().out
    assert f"Deleting subnet '{subnet_id}' in {region}..." in output
    assert "Looking for associated route tables..." in output
    assert f"Route tables associated with subnet '{subnet_id}':" in output
    assert route_table_id in output
    assert f"Disassociating route tables from subnet '{subnet_id}'..." in output
    assert f"Route table {route_table_id} was successfully disassociated from subnet '{subnet_id}'"
    assert "Initiating subnet deletion..." in output
    assert f"Subnet '{subnet_id}' was successfully deleted" in output
    assert result is None

    # Confirm deletion
    subnets = client.describe_subnets()["Subnets"]
    assert not any(s["SubnetId"] == subnet_id for s in subnets)


################################### delete_vpc_endpoint tests ######################################
@mock_aws
def test_delete_vpc_endpoint(capsys):
    region = "us-east-1"
    client = boto3.client("ec2", region_name=region)

    # Create a VPC
    vpc_response = client.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = vpc_response["Vpc"]["VpcId"]
    logger.debug(f"VPC ID for test: {vpc_id}")

    # Get route table ID
    route_table_id = client.describe_route_tables(Filters=[{"Name": "association.main", "Values": ["true"]}])["RouteTables"][0][
        "RouteTableId"
    ]
    logger.debug(f"Route table ID for test: {route_table_id}")

    # Create a subnet
    subnet_response = client.create_subnet(VpcId=vpc_id, CidrBlock="10.0.0.0/24")
    subnet_id = subnet_response["Subnet"]["SubnetId"]
    logger.debug(f"Subnet ID for test: {subnet_id}")

    # Create a VPC endpoint
    vpc_endpoint_response = client.create_vpc_endpoint(
        VpcId=vpc_id,
        ServiceName="com.amazonaws.us-east-1.s3",
        VpcEndpointType="Gateway",
        RouteTableIds=[route_table_id],
    )
    endpoint_id = vpc_endpoint_response["VpcEndpoint"]["VpcEndpointId"]
    arn = f"arn:aws:ec2:{region}:123456789012:vpc-endpoint/{endpoint_id}"
    logger.debug(f"VPC Endpoint ID for test: {endpoint_id}")

    # Confirm it exists
    vpc_endpoints = client.describe_vpc_endpoints()["VpcEndpoints"]
    assert any(v["VpcEndpointId"] == endpoint_id for v in vpc_endpoints)

    result = delete_functions.delete_vpc_endpoint(arn, region)
    output = capsys.readouterr().out

    assert f"Deleting VPC endpoint '{endpoint_id}' in {region}..." in output
    assert f"VPC endpoint '{endpoint_id}' was successfully deleted" in output
    assert result is None

    # Confirm deletion
    response = client.describe_vpc_endpoints()
    logger.debug("Describe VPC Endpoints Response:")
    logger.debug(json.dumps(response, indent=4, default=str))

    vpc_endpoints = response.get("VpcEndpoints", [])
    if vpc_endpoints and vpc_endpoints[0]["VpcEndpointId"] == endpoint_id:
        assert vpc_endpoints[0]["State"] == "deleted"
