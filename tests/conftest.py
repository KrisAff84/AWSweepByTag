"""
  Common configurations for tests

  Sets up logger, fixtures, helper functions, and common exceptions that can be used across multiple test files.

  Fixtures:
    - setup
    - vpc
    - subnet
    - route_table
    - instance

  Helpers:
    - create_arn

  Common Exceptions:
    - throttling_exception
"""

import logging
import os

import boto3
import botocore.exceptions
import pytest
from moto import mock_aws

from awsweepbytag.logger import get_colored_stream_handler

log_level_str = os.getenv("LOG_LEVEL", "WARNING").upper()
log_level = getattr(logging, log_level_str)

logger = logging.getLogger(__name__)
logger.setLevel(log_level)

if not logger.handlers:
    logger.addHandler(get_colored_stream_handler())


####################################### Fixtures/Reusable Functions ########################################
def create_arn(service: str, region: str, resource_type: str, resource_id: str, account_id: str = "123456789012"):
    return f"arn:aws:{service}:{region}:{account_id}:{resource_type}/{resource_id}"


@pytest.fixture(scope="function")
def setup():
    with mock_aws():
        region = "us-east-1"
        client = boto3.client("ec2", region_name=region)
        yield region, client


@pytest.fixture(scope="function")
def vpc(setup):
    region, client = setup
    response = client.create_vpc(CidrBlock="10.0.0.0/16")
    vpc_id = response["Vpc"]["VpcId"]
    arn = create_arn("ec2", region, "vpc", vpc_id)
    yield region, client, arn, vpc_id


@pytest.fixture(scope="function")
def subnet(vpc):
    region, client, _, vpc_id = vpc
    subnet_id = client.create_subnet(VpcId=vpc_id, CidrBlock="10.0.0.0/24")["Subnet"]["SubnetId"]
    arn = create_arn("ec2", region, "subnet", subnet_id)

    subnets = client.describe_subnets()["Subnets"]
    assert any(s["SubnetId"] == subnet_id for s in subnets)

    yield region, client, arn, subnet_id, vpc_id


@pytest.fixture(scope="function")
def route_table(vpc):
    region, client, _, vpc_id = vpc
    route_table_id = client.create_route_table(VpcId=vpc_id)["RouteTable"]["RouteTableId"]
    arn = create_arn("ec2", region, "route-table", route_table_id)

    # Confirm route table exists
    route_tables = client.describe_route_tables()["RouteTables"]
    assert any(r["RouteTableId"] == route_table_id for r in route_tables)

    yield region, client, arn, route_table_id, vpc_id


@pytest.fixture(scope="function")
def instance(setup):
    region, client = setup
    response = client.run_instances(ImageId="ami-05f417c208be02d4d", InstanceType="t2.nano", MinCount=1, MaxCount=1)
    instance_id = response["Instances"][0]["InstanceId"]
    arn = create_arn("ec2", region, "instance", instance_id)

    instances = client.describe_instances()["Reservations"][0]["Instances"]
    assert any(i["InstanceId"] == instance_id for i in instances)

    yield region, client, arn, instance_id


################################### Common Exceptions ####################################
def throttling_exception(operation_name: str="GenericOperation", *args, **kwargs):
    raise botocore.exceptions.ClientError({"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}}, operation_name)


# def not_found_exception(*args, **kwargs):
#     raise botocore.exceptions.ClientError({"Error": {"Code": "NotFoundException", "Message": "Not found"}}, "DeleteLaunchTemplate")
