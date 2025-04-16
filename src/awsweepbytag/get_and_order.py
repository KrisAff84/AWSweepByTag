import json
import time

import boto3
import botocore.exceptions

from awsweepbytag import get_other_ids
from awsweepbytag import text_formatting as tf


def get_resources_by_tag(tag_key: str, tag_value: str, regions: list[str]) -> list[dict[str, str]]:
    """
    Get list of resources by common tag key and value.

    Accepts a tag key and value, as well as a list of regions to search for resources in.
    The function then calls the resource-groups client to search for resources with the
    given tag key and value for each region provided. All required arguments are retrieved
    and passed through prompts in the main function.

    Args:
        tag_key (str): Tag key to search for resources by.
        tag_value (str): Tag value to search for resources by.
        regions (list[str]): List of regions to search for resources in.

    Returns:
        list[dict[str, str]] - List of dictionaries containing resource information.
            \nEach dictionary contains the following keys:
                - ResourceArn (str): ARN of the resource.
                - ResourceType (str): Type of the resource.
                - Region (str): Region where the resource is located.
    """

    resources = []
    for region in regions:

        client = boto3.client("resource-groups", region_name=region)

        query = {
            "Type": "TAG_FILTERS_1_0",
            "Query": json.dumps(
                {
                    "ResourceTypeFilters": ["AWS::AllSupported"],
                    "TagFilters": [{"Key": tag_key, "Values": [tag_value]}],
                }
            ),
        }

        try:
            response = client.search_resources(
                ResourceQuery=query,
                MaxResults=50,
            )
            while True:
                for res in response.get("ResourceIdentifiers", []):
                    res["Region"] = region
                    resources.append(res)

                next_token = response.get("NextToken")
                if not next_token:
                    break

                # Retrieve additional results if NextToken is present
                response = client.search_resources(ResourceQuery=query, MaxResults=50, NextToken=next_token)

        except botocore.exceptions.ClientError as e:
            print()
            error_message = e.response.get("Error", {}).get("Message", "")
            tf.failure_print(f"Error querying resources in region '{region}':")
            tf.indent_print(f"{e}\n", 8)

            if "token included in the request is invalid" in error_message:
                tf.indent_print(
                    "The provided token is invalid. You may need to enable region '{region}' in your AWS account.\n",
                    8,
                )

            else:
                tf.indent_print("Error:")
                tf.indent_print(f"{e}")
            continue

        time.sleep(0.2)
    return resources


def get_other_resources(tag_key: str, tag_value: str, regions: list[str]) -> list[dict[str, str]]:
    """
    Get other resources that are not present when using the 'resource-groups' client.

    Calls various other functions that can obtain resource information by tag key and
    value, even if they are not present when using the 'resource-groups' client. Presently
    it calls get_autoscaling_groups. Other resources may be added in the future as needed.

    Args:
        tag_key (str): Tag key.
        tag_value (str): Tag value.
        regions (list[str]): List of regions to search for resources in.

    Returns:
        list[dict[str, str]] - List of dictionaries containing resource information.
            \nEach dictionary contains the following keys:
            - resource_type (str): Type of the resource.
            - resource_id (optional(str)): ID of the resource. Present if arn is not.
            - arn (optional(str)): ARN of the resource. Present if resource_id is not.
            - service (str): Service that the resource belongs to.
            - region (str): Region where the resource is located.
    """

    resources = []

    autoscaling_groups = get_other_ids.get_autoscaling_groups(tag_key, tag_value, regions)
    resources.extend(autoscaling_groups)

    return resources


def parse_resource_by_type(resource: dict[str, str]) -> dict[str, str]:
    """
    Parse resource by type, ARN, service, and region to return a standardized dictionary

    Parsing is needed so that each resource can be mapped to the appropriate deletion function.
    Before processing, each resource takes on the following format:

        {
            'ResourceArn': 'arn:aws:...',
            'ResourceType': 'AWS::Service::ResourceType',
            'Region': 'us-west-2'
        }

    After processing, the format will change to the following:

        {
            'resource_type': 'resourcetype',
            'arn': 'arn:aws:...', # This field could be 'arn' or 'resource_id' depending on the service
            'service': 'service',
            'region': 'us-west-2'
        }

    Args:
        resource (dict[str, str]): Dictionary containing resource information.
            \nThe resource dictionary should contain the following keys:
            - ResourceArn (str): ARN of the resource.
            - ResourceType (str): Type of the resource.
            - Region (str): Region where the resource is located.

    Returns:
        dict[str, str] - Dictionary containing parsed resource information.
            \nEach dictionary contains the following keys:
            - resource_type (str): Type of the resource.
            - arn (str): ARN of the resource.
            - service (str): Service that the resource belongs to.
            - region (str): Region where the resource is located.
    """

    arn = resource["ResourceArn"]
    service = (resource["ResourceType"].split("::")[1]).lower()
    resource_type = (resource["ResourceType"].split("::")[2]).lower()
    region = resource["Region"]
    resource_for_deletion = {
        "resource_type": resource_type,
        "arn": arn,
        "service": service,
        "region": region,
    }
    return resource_for_deletion


def order_resources_for_deletion(
    resources: list[dict[str, str]],
) -> list[dict[str, str]]:
    """
    Orders resources for deletion based on their potential dependencies

    1. Application autoscaling resources are removed - their deletion is handled when the resource they are scaling is deleted.
    2. Resources are then grouped into 4 lists based on their deletion order:

        1. Networking resources - must be ordered internally + they need to be placed last since other resources depend on them
        2. Other resources that must follow a deletion order - currently this includes ELBs (and associated resources) and ASGs
        3. Resources that do not contain an arn (e.g., snapshots, AMIs) - Can be deleted at any time
        4. Other resources - Can be deleted at any time

    3. Resources are ordered based based on order of deletion and returned

    Args:
        resources (list[dict[str, str]]): List of resources to be deleted.

    Returns:
        list[dict[str, str]] - Ordered list of resources to be deleted.
    """

    # Remove application autoscaling resource from the list - any application autoscaling resource is deleted when the resource it is scaling is deleted
    resources = [r for r in resources if r.get("service") != "applicationautoscaling"]

    ############ Group the resources into larger groups of similar category ##############

    # Networking resources that must follow a particular deletion order - These need to be deleted last since other resources depend on them
    # Additionally, resources in this group need to follow a strict internal deletion order as well
    # EC2 instance is the exception in this group since it is not a networking resource, but is shares the same service type ("ec2")
    ordered_networking_resources = [
        r
        for r in resources
        if r["service"] == "ec2"
        and (
            r["resource_type"]
            in (
                "eip",
                "instance",
                "internetgateway",
                "natgateway",
                "routetable",
                "subnet",
                "securitygroup",
                "transitgatewayattachment",
                "vpcendpoint",
                "vpc",
            )
        )
    ]

    # Other resources that must follow a particlar deletion order but are not networking resources
    ordered_non_networking_resources = [
        r
        for r in resources
        if (
            r["service"]
            in (
                "elasticloadbalancingv2",
                "autoscaling",
            )
        )
    ]

    # Resources that have a `resource_id` instead of an ARN (e.g., snapshots, AMIs)
    # May rename to snapshots_and_images in the future if these end up being the only resources with resource_id
    other_resources = [
        r for r in resources if "resource_id" in r and r not in ordered_networking_resources and r not in ordered_non_networking_resources
    ]

    # Remaining resources that are not part of the above groups - these (along with other_resources) can be deleted first since no other resource depends on them
    non_ordered_resources = [
        r
        for r in resources
        if r not in ordered_networking_resources and r not in ordered_non_networking_resources and r not in other_resources
    ]

    ordered_resources = []
    ordered_resources.extend(non_ordered_resources)
    ordered_resources.extend(other_resources)
    ordered_resources.extend([r for r in ordered_non_networking_resources if r["service"] == "autoscaling"])
    ordered_resources.extend([r for r in ordered_non_networking_resources if "loadbalancer" in r["resource_type"]])
    ordered_resources.extend([r for r in ordered_non_networking_resources if "listener" in r["resource_type"]])
    ordered_resources.extend([r for r in ordered_non_networking_resources if "targetgroup" in r["resource_type"]])
    ordered_resources.extend([r for r in ordered_networking_resources if r["resource_type"] == "instance"])
    ordered_resources.extend([r for r in ordered_networking_resources if r["resource_type"] == "vpcendpoint"])
    ordered_resources.extend([r for r in ordered_networking_resources if r["resource_type"] == "natgateway"])
    ordered_resources.extend([r for r in ordered_networking_resources if r["resource_type"] == "subnet"])
    ordered_resources.extend([r for r in ordered_networking_resources if r["resource_type"] == "eip"])
    ordered_resources.extend([r for r in ordered_networking_resources if r["resource_type"] == "internetgateway"])
    ordered_resources.extend([r for r in ordered_networking_resources if r["resource_type"] == "routetable"])
    ordered_resources.extend([r for r in ordered_networking_resources if r["resource_type"] == "securitygroup"])
    ordered_resources.extend([r for r in ordered_networking_resources if r["resource_type"] == "vpc"])

    return ordered_resources
