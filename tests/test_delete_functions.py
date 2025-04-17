from unittest.mock import patch

import boto3
import botocore.exceptions
import pytest
from moto import mock_aws

from awsweepbytag import delete_functions


################################### Common Exceptions ####################################
def throttling_exception(*args, **kwargs):
    raise botocore.exceptions.ClientError({"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, "DeleteLaunchTemplate")


def not_found_exception(*args, **kwargs):
    raise botocore.exceptions.ClientError({"Error": {"Code": "NotFoundException", "Message": "Not found"}}, "DeleteLaunchTemplate")


################################### delete_launch_template tests ######################################
@mock_aws
def test_delete_launch_template_success(capsys):
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

    assert "ThrottlingException" in str(exc_info.value)
