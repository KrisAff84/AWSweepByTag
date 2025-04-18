import json
import logging
from unittest.mock import patch

import boto3
import botocore.exceptions
import pytest
from moto import mock_aws

from awsweepbytag import delete_functions

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


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
    arn = f"arn:aws:ec2:{region}:123456789012:instance/{instance_id}"

    # Confirm it exists
    instances = client.describe_instances()["Reservations"][0]["Instances"]
    logger.debug("Instance for test:")
    logger.debug(json.dumps(instances, indent=2, default=str))
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
    arn = f"arn:aws:ec2:{region}:123456789012:instance/{instance_id}"

    # Confirm it exists
    instances = client.describe_instances()["Reservations"][0]["Instances"]
    logger.debug("Instance for test:")
    logger.debug(json.dumps(instances, indent=2, default=str))
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
