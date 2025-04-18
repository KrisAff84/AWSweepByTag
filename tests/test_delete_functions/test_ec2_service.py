# import json
import logging
from unittest.mock import patch

import boto3
import botocore.exceptions
import pytest
from moto import mock_aws

from awsweepbytag import delete_functions
from awsweepbytag.logger import get_colored_stream_handler

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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
    logger.debug("Starting test_deregister_ami")
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
    logger.debug("Starting test_delete_ec2_instance")
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
    logger.debug("Starting test_delete_ec2_instance_not_found")
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
    logger.debug("Starting test_delete_ec2_instance_state_shutting_down")
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
    logger.debug("Starting test_delete_ec2_instance_autoscaling_true")
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
    logger.debug("Starting test_release_eip")
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
    logger.debug("Starting test_delete_internet_gateway")
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
    logger.debug("Starting test_delete_launch_template")
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
    logger.debug("Starting test_delete_launch_template_not_found")
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
    logger.debug("Starting test_delete_launch_template_throttling")
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
