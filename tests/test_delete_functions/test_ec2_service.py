"""
Tests for EC2 service resources in delete_functions.py

The following functions are tested:
- deregister_ami
- delete_ec2_instance
- release_eip
- delete_internet_gateway
- delete_launch_template
- delete_nat_gateway
- delete_network_interface
- delete_route_table
- delete_security_group
- delete_snapshot
- delete_subnet
- delete_vpc_endpoint
- delete_vpc

"""

import json
from unittest.mock import patch

import botocore.exceptions
import pytest
from moto import mock_aws

from awsweepbytag import delete_functions as df
from tests.conftest import create_arn, logger, throttling_exception


################################### deregister_ami tests ######################################
def test_deregister_ami(capsys, instance):
    region, client, _, instance_id = instance

    # Create an AMI
    create_response = client.create_image(Name="test-image", InstanceId=instance_id)
    ami_id = create_response["ImageId"]
    arn = create_arn("ec2", region, "image", ami_id)
    logger.debug(f"AMI ARN for test: {arn}")

    # Confirm it exists
    images = client.describe_images()["Images"]
    assert any(i["ImageId"] == ami_id for i in images)

    # Run delete function
    result = df.deregister_ami(arn, region)
    output = capsys.readouterr().out
    assert f"AMI '{ami_id}' was successfully deregistered" in output
    assert result is None

    # Confirm it was deleted
    images = client.describe_images()["Images"]
    assert not any(i["ImageId"] == ami_id for i in images)


################################### delete_ec2_instance tests ######################################
def test_delete_ec2_instance(capsys, instance):
    region, client, arn, instance_id = instance

    # Run delete function
    result = df.delete_ec2_instance(arn, region)
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
def test_delete_ec2_instance_not_found(capsys, setup):
    region, _ = setup
    instance_id = "i-0b3697156fd669628"
    arn = create_arn("ec2", region, "instance", instance_id)

    result = df.delete_ec2_instance(arn, region)

    # Assert correct message was printed
    output = capsys.readouterr().out
    assert f"Terminating EC2 instance '{instance_id}' in {region}..." in output
    assert f"EC2 instance '{instance_id}' not found. It may have already been terminated." in output
    assert result is None


@mock_aws
@patch("boto3.client")
def test_delete_ec2_instance_state_shutting_down(mock_boto_client, capsys, setup):
    # Arrange
    region, _ = setup
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

    arn = create_arn("ec2", region, "instance", instance_id)
    result = df.delete_ec2_instance(arn, region)
    output = capsys.readouterr().out

    assert f"Current status of EC2 instance '{instance_id}' is: '{instance_status}'. Skipping..." in output
    assert f"EC2 instance '{instance_id}' is shutting down." not in output
    assert result is None


def test_delete_ec2_instance_autoscaling_true(capsys, instance):
    region, client, arn, instance_id = instance
    logger.debug(f"Instance ID for test: {instance_id}")

    # Run delete function
    result = df.delete_ec2_instance(arn, region, True)
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
def test_release_eip(capsys, setup):
    region, client = setup
    # Create an EIP
    create_response = client.allocate_address(Domain="vpc")
    eip_id = create_response["AllocationId"]
    arn = create_arn("ec2", region, "eip-allocation", eip_id)

    # Confirm it exists
    eips = client.describe_addresses()["Addresses"]
    assert any(e["AllocationId"] == eip_id for e in eips)

    # Run delete function
    result = df.release_eip(arn, region)
    output = capsys.readouterr().out
    assert f"Elastic IP '{eip_id}' was successfully released" in output
    assert result is None

    # Confirm it was deleted
    eips = client.describe_addresses()["Addresses"]
    assert not any(e["AllocationId"] == eip_id for e in eips)


################################### delete_internet_gateway tests ######################################
def test_delete_internet_gateway(capsys, vpc):
    region, client, arn, vpc_id = vpc
    logger.debug(f"VPC ID for test: {vpc_id}")

    # Create an IGW
    gateway_id = client.create_internet_gateway()["InternetGateway"]["InternetGatewayId"]
    arn = create_arn("ec2", region, "igw", gateway_id)
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

    result = df.delete_internet_gateway(arn, region)
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
def test_delete_launch_template(capsys, setup):
    region, client = setup
    # Create a launch template
    create_response = client.create_launch_template(
        LaunchTemplateName="test-template", LaunchTemplateData={"ImageId": "ami-12345678", "InstanceType": "t2.nano"}
    )

    template_id = create_response["LaunchTemplate"]["LaunchTemplateId"]
    arn = create_arn("ec2", region, "launch-template", template_id)

    # Confirm it exists
    templates = client.describe_launch_templates()["LaunchTemplates"]
    assert any(t["LaunchTemplateId"] == template_id for t in templates)

    # Run delete function
    result = df.delete_launch_template(arn, region)
    output = capsys.readouterr().out
    assert f"Launch template '{template_id}' was successfully deleted" in output
    assert result is None
    # print(output)

    # Confirm it was deleted
    templates = client.describe_launch_templates()["LaunchTemplates"]
    assert not any(t["LaunchTemplateId"] == template_id for t in templates)


def test_delete_launch_template_not_found(capsys, setup):
    region, _ = setup
    # Arrange
    template_id = "lt-0abcd1234efgh5678"
    arn = f"arn:aws:ec2:{region}::launch-template/{template_id}"

    # Moto starts with no templates — deletion of this should raise ClientError with code InvalidLaunchTemplateId.NotFound
    # Act
    result = df.delete_launch_template(arn, region)

    # Assert function returns None
    assert result is None

    # Assert correct message was printed
    output = capsys.readouterr().out
    assert f"Launch template '{template_id}' not found. It may have already been deleted." in output
    assert result is None
    # print(output)


@patch("boto3.client")
def test_delete_launch_template_throttling(mock_boto_client, capsys, setup):
    region, _ = setup

    # Arrange
    mock_client = mock_boto_client.return_value
    mock_client.delete_launch_template.side_effect = lambda *args, **kwargs: throttling_exception("DeleteLaunchTemplate")

    lt_id = "lt-0123456789abcdef0"
    arn = create_arn("ec2", region, "launch-template", lt_id)

    # Act + Assert
    with pytest.raises(botocore.exceptions.ClientError) as exc_info:
        df.delete_launch_template(arn, region)
    output = capsys.readouterr().out
    assert f"Deleting Launch Template '{lt_id}' in {region}..." in output

    assert "ThrottlingException" in str(exc_info.value)


################################### delete_nat_gateway tests ######################################
def test_delete_nat_gateway(capsys, subnet):
    region, client, _, subnet_id, _ = subnet
    logger.debug(f"Subnet ID for test: {subnet_id}")

    # Create a NAT gateway
    nat_gateway_id = client.create_nat_gateway(SubnetId=subnet_id)["NatGateway"]["NatGatewayId"]
    arn = create_arn("ec2", region, "natgateway", nat_gateway_id)
    logger.debug(f"NAT Gateway ID for test: {nat_gateway_id}")

    # Confirm it exists
    nat_gateways = client.describe_nat_gateways()["NatGateways"]
    assert any(n["NatGatewayId"] == nat_gateway_id for n in nat_gateways)

    # Run delete function
    result = df.delete_nat_gateway(arn, region)
    output = capsys.readouterr().out
    assert f"Deleting Nat Gateway '{nat_gateway_id}' in {region}..." in output
    assert f"Nat gateway '{nat_gateway_id}' deletion initiated" in output
    assert "Waiting for NAT Gateway to complete deletion process..." in output
    assert f"Nat gateway '{nat_gateway_id}' has been fully deleted" in output
    assert result is None


################################### delete_route_table tests ######################################
def test_delete_route_table(capsys, route_table):
    region, client, arn, route_table_id, _ = route_table
    logger.debug(f"Route table ID for test: {route_table_id}")

    # Run delete function
    result = df.delete_route_table(arn, region)
    output = capsys.readouterr().out
    assert f"Deleting route table '{route_table_id}' in {region}..." in output
    assert f"Route table '{route_table_id}' was successfully deleted" in output
    assert result is None

    # Confirm deletion
    route_tables = client.describe_route_tables()["RouteTables"]
    assert not any(r["RouteTableId"] == route_table_id for r in route_tables)


################################### delete_security_group tests ######################################
def test_delete_security_group(capsys, vpc):
    region, client, arn, vpc_id = vpc
    logger.debug(f"VPC ID for test: {vpc_id}")

    # Create a security group
    sg_id = client.create_security_group(GroupName="test-group", Description="Test group")["GroupId"]
    arn = create_arn("ec2", region, "security-group", sg_id)
    logger.debug(f"Security group ID for test: {sg_id}")

    # Confirm it exists
    groups = client.describe_security_groups()["SecurityGroups"]
    assert any(g["GroupId"] == sg_id for g in groups)

    # Run delete function
    result = df.delete_security_group(arn, region)
    output = capsys.readouterr().out
    assert f"Deleting security group '{sg_id}' in {region}..." in output
    assert f"Security group '{sg_id}' was successfully deleted" in output
    assert result is None

    # Confirm deletion
    security_groups = client.describe_security_groups()["SecurityGroups"]
    assert not any(g["GroupId"] == sg_id for g in security_groups)


################################### delete_snapshot tests ######################################
def test_delete_snapshot(capsys, setup):
    region, client = setup

    # Create a volume
    volume_id = client.create_volume(Size=1, AvailabilityZone=f"{region}a")["VolumeId"]

    # Create a snapshot
    snapshot_id = client.create_snapshot(VolumeId=volume_id)["SnapshotId"]
    arn = create_arn("ec2", region, "snapshot", snapshot_id)
    logger.debug(f"Snapshot ID for test: {snapshot_id}")

    # Confirm it exists
    snapshots = client.describe_snapshots(SnapshotIds=[snapshot_id])["Snapshots"]
    assert any(s["SnapshotId"] == snapshot_id for s in snapshots)

    # Run delete function
    result = df.delete_snapshot(arn, region)
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
def test_delete_subnet_with_route_table_association(capsys, subnet, route_table):
    region, client, arn, subnet_id, _ = subnet
    _, _, _, route_table_id, _ = route_table

    # Associate route table with subnet
    client.associate_route_table(RouteTableId=route_table_id, SubnetId=subnet_id)

    # Confirm route table is associated with subnet
    route_tables = client.describe_route_tables()["RouteTables"]
    subnet_route_table_id = next(
        (rt["RouteTableId"] for rt in route_tables for assoc in rt.get("Associations", []) if assoc.get("SubnetId") == subnet_id), None
    )
    assert subnet_route_table_id == route_table_id

    # Run delete function
    result = df.delete_subnet(arn, region)
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
def test_delete_vpc_endpoint(capsys, subnet):
    region, client, _, subnet_id, vpc_id = subnet
    logger.debug(f"VPC ID for test: {vpc_id}")
    logger.debug(f"Subnet ID for test: {subnet_id}")

    # Get route table ID
    route_table_id = client.describe_route_tables(
        Filters=[{"Name": "association.main", "Values": ["true"]}, {"Name": "vpc-id", "Values": [vpc_id]}]
    )["RouteTables"][0]["RouteTableId"]
    logger.debug(f"Route table ID for test: {route_table_id}")

    # Create a VPC endpoint
    vpc_endpoint_response = client.create_vpc_endpoint(
        VpcId=vpc_id,
        ServiceName="com.amazonaws.us-east-1.s3",
        VpcEndpointType="Gateway",
        RouteTableIds=[route_table_id],
    )
    endpoint_id = vpc_endpoint_response["VpcEndpoint"]["VpcEndpointId"]
    arn = create_arn("ec2", region, "vpc-endpoint", endpoint_id)
    logger.debug(f"VPC Endpoint ID for test: {endpoint_id}")

    # Confirm it exists
    vpc_endpoints = client.describe_vpc_endpoints()["VpcEndpoints"]
    assert any(v["VpcEndpointId"] == endpoint_id for v in vpc_endpoints)

    result = df.delete_vpc_endpoint(arn, region)
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


################################### delete_vpc tests ######################################
def test_delete_vpc(capsys, vpc):
    region, client, arn, vpc_id = vpc
    logger.debug(f"VPC ID for test: {vpc_id}")

    # Confirm it exists
    vpcs = client.describe_vpcs()["Vpcs"]
    assert any(v["VpcId"] == vpc_id for v in vpcs)

    # Run delete function
    result = df.delete_vpc(arn, region)
    output = capsys.readouterr().out
    assert f"Deleting VPC '{vpc_id}' in {region}..." in output
    assert f"Checking VPC '{vpc_id}' for security groups..." in output
    assert "Deleting VPC..." in output
    assert f"VPC '{vpc_id}' was successfully deleted" in output
    logger.debug(output)
    assert result is None

    # Confirm deletion
    vpcs = client.describe_vpcs()["Vpcs"]
    assert not any(v["VpcId"] == vpc_id for v in vpcs)
