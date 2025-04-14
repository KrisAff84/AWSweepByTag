import json
import time
import boto3
import botocore.exceptions
import delete_resource_map as drmap
from delete_functions import disable_cloudfront_distribution, wait_for_distribution_disabled, delete_cloudfront_distribution
import get_other_ids
import text_formatting as tf


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

        client = boto3.client('resource-groups', region_name=region)

        query = {
            "Type": "TAG_FILTERS_1_0",
            "Query": json.dumps({
                "ResourceTypeFilters": ["AWS::AllSupported"],
                "TagFilters": [{
                    "Key": tag_key,
                    "Values": [tag_value]
                }]
            })
        }

        try:
            response = client.search_resources(
                ResourceQuery=query,
                MaxResults=50,
            )
            while True:
                for res in response.get('ResourceIdentifiers', []):
                    res['Region'] = region
                    resources.append(res)

                next_token = response.get('NextToken')
                if not next_token:
                    break

                # Retrieve additional results if NextToken is present
                response = client.search_resources(
                    ResourceQuery=query,
                    MaxResults=50,
                    NextToken=next_token
                )

        except botocore.exceptions.ClientError as e:
            print(f"Error querying resources in region {region}: {e}")
            continue

        time.sleep(0.2)

    return resources


def get_other_resources(tag_key: str, tag_value: str, regions: list[str]) -> list[dict[str, str]]:
    """
    Get other resources that are not present when using the 'resource-groups' client.

    Calls various other functions that can obtain resource information by tag key and
    value, even if they are not present when using the 'resource-groups' client. Presently
    it calls get_images (which retrieves images and snapshots) and get_autoscaling_groups.
    Other resources may be added in the future as needed.

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
    images_and_snapshots = get_other_ids.get_images(tag_key, tag_value, regions)
    resources.extend(images_and_snapshots)

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

    arn = resource['ResourceArn']
    service = (resource['ResourceType'].split('::')[1]).lower()
    resource_type = (resource['ResourceType'].split('::')[2]).lower()
    region = resource['Region']
    resource_for_deletion = {
        'resource_type': resource_type,
        'arn': arn,
        'service': service,
        'region': region
    }
    return resource_for_deletion


def order_resources_for_deletion(resources: list[dict[str, str]]) -> list[dict[str, str]]:
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
        r for r in resources
        if r["service"] == "ec2" and (
            r['resource_type'] in (
                'eip',
                "instance",
                'internetgateway',
                'natgateway',
                'routetable',
                'subnet',
                'transitgatewayattachment',
                'vpcendpoint',
                'vpc',
            )
        )
    ]

    # Other resources that must follow a particlar deletion order but are not networking resources
    ordered_non_networking_resources = [
        r for r in resources
        if (r["service"] in (
            "elasticloadbalancingv2",
            "autoscaling",
            )
        )
    ]

    # Resources that have a `resource_id` instead of an ARN (e.g., snapshots, AMIs)
    # May rename to snapshots_and_images in the future if these end up being the only resources with resource_id
    other_resources = [
        r for r in resources
        if "resource_id" in r
        and r not in ordered_networking_resources
        and r not in ordered_non_networking_resources
    ]

    # Remaining resources that are not part of the above groups - these (along with other_resources) can be deleted first since no other resource depends on them
    non_ordered_resources = [
        r for r in resources
        if r not in ordered_networking_resources
        and r not in ordered_non_networking_resources
        and r not in other_resources
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
    ordered_resources.extend([r for r in ordered_networking_resources if r["resource_type"] == "vpc"])

    return ordered_resources


def delete_resource(resource: dict[str, str]) -> list[dict[str, str]] | None:
    """
    Finds and calls the appropriate delete function based on the resource type

    This function performs the following steps:

    1. The resource is checked to see if it is a CloudFront distribution.
    2. If the resource is a CloudFront distribution, disable_cloudfront_distribution is called -> resource is returned for attempted deletion with the retry function.
    3. If the resource is not a CloudFront distribution, the DELETE_FUNCTIONS dictionary is checked to see if a delete function exists for the resource
    4. If a delete function exists, it is called -> ancillary resources can be returned if they were not successfully deleted.
    5. If a delete function does not exist, a message is printed and the resource is skipped.

        - Example: If an API GW is the main resource to delete, any VPC links will be attempted to be deleted as well.
        If they are not successfully deleted they will be returned by the resource delete function to be retried by the retry function.
        Unsuccessful "main" resources (API GW in the above example) will raise an exception in their delete function, and be returned by this function.

    Args:
        resource (dict[str, str]): Dictionary containing resource information.

    Returns:
        list[dict[str, str]] | None: List of resources that were not successfully deleted, or None if all resources were successfully deleted.

    Raises:
        None

        - Exceptions are handled by returning resources to be retried by the retry function, unless the exception is one of the following,
        in which case a message is printed and None is returned:

            - NotFoundException
            - NoSuchEntity
            - ResourceNotFoundException
    """

    service = resource['service']
    resource_type = resource['resource_type']
    arn = resource.get('arn') or resource.get('resource_id')
    region = resource['region']

    # print(f"DEBUG: Checking DELETE_FUNCTIONS for service='{service}', resource_type='{resource_type}'")

    # CloudFront distributions are handled differently than other resources since disabling them can take several minutes.
    # The disable_cloudfront_distribution will attempt to delete if it is already disabled, otherwise it will return retry = True
    # which allows it to be retried later.
    if resource_type == "distribution":
        retry = disable_cloudfront_distribution(arn)
        if retry:
            return [resource]
        else:
            return None

    if service in drmap.DELETE_FUNCTIONS and resource_type in drmap.DELETE_FUNCTIONS[service]:
        try:
            resources = drmap.DELETE_FUNCTIONS[service][resource_type](arn, region) # Make sure a list[dict] is returned from delete functions
            if resources:
                return resources
            else:
                return None

        except botocore.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')

            # These exceptions will not be handled by the retry function since they indicate the resource does not exist
            if error_code in ["NotFoundException", "NoSuchEntity", "ResourceNotFoundException"]:
                tf.indent_print(f"Resource '{arn}' not found. It may have already been deleted. Skipping...")
                return None

            # These exceptions will be handled by the retry function
            if error_code in ["DependencyViolation", "TooManyRequestsException", "ThrottlingException", "ServiceUnavailableException"]:
                tf.failure_print(f"Resource '{arn}' could not be deleted due to a {error_code}. Retrying later...")
                return [resource]  # Return to main function for retry

            # Unknown exceptions to be handled by retry function for good measure
            tf.failure_print(f"Resource '{arn}' could not be deleted. Error:")
            tf.indent_print(e, 6)
            tf.indent_print("Retrying later...")
            return [resource]

    else:
        tf.header_print(f"No delete function found for {service}::{resource_type}. Resource must be deleted manually\n")
        return None

# Need to print a statement when all resources have been deleted
def retry_failed_deletions(failed_resources: list[dict[str, str]], max_retries: int=6, wait_time: int=10) -> None:
    """
    Retries failed deletions up to max_retries times

    CloudFront distributions are handled differently than other resources.
        - In the main delete function (delete_resources), the distribution is disabled, unless it has already been disabled in which case it is deleted.
        - In this function, a waiter is called to wait for the distribution to be disabled.
        - After the distribution is disabled, it is deleted.

    Other Resources:
        - The retry function is called for each resource that was not successfully deleted.
        - If the resource is not successfully deleted the first time, it is retried up to max_retries times.
        - If there are resources that have not successfully deleted after max_retries, they are printed to the console and the function completes.

    Args:
        failed_resources (list[dict[str, str]]): List of resources that were not successfully deleted.
        max_retries (int, optional): Maximum number of retries. Defaults to 6.
        wait_time (int, optional): Time (seconds) to wait between retries. Defaults to 10.

    Returns:
        None

    """

    # Separate CloudFront distributions from other resources
    cloudfront_resources = [r for r in failed_resources if r.get("resource_type") == "distribution"]
    other_resources = [r for r in failed_resources if r.get("resource_type") != "distribution"]

    # Handle CloudFronts first
    for resource in cloudfront_resources:
        try:
            wait_for_distribution_disabled(resource['arn'])
            delete_cloudfront_distribution(resource['arn'])
        except Exception as e:
            tf.failure_print(f"Error deleting CloudFront distribution {resource['arn']} on retry: {str(e)}")
            other_resources.append(resource)  # Add it back for retry if it still fails

    if other_resources == []:
        return

    # Retry loop for everything else
    for attempt in range(1, max_retries + 1):
        tf.header_print(f"Retry attempt {attempt}/{max_retries} for failed deletions...")
        new_failed_resources = []

        for resource in other_resources:
            if isinstance(resource, str):
                print(f"Skipping invalid resource: {resource}")
                continue

            try:
                result = delete_resource(resource)
                if result:
                    new_failed_resources.append(result)

            except botocore.exceptions.ClientError as e:
                if "DependencyViolation" in str(e):
                    new_failed_resources.append(resource)
                else:
                    tf.failure_print(f"Fail from retry function: Failed to delete {resource['arn']}", 0)

        if not new_failed_resources:
            tf.success_print("All resources were successfully deleted.", 0)
            return

        other_resources = new_failed_resources
        print(f"{len(other_resources)} resources still cannot be deleted. Retrying in {wait_time} seconds...\n")
        time.sleep(wait_time)

    if other_resources:
        tf.failure_print(f"\nFinal retry attempt reached. {len(other_resources)} resources could not be deleted.", 0)
        print("Resources that could not be deleted:\n")
        for resource in other_resources:
            tf.response_print(json.dumps(resource, indent=4, default=str), 4)


def main():
    tag_key = input("Enter the tag key to search by: ")
    tag_value = input("Enter the tag value to search by: ")
    regions = [r.strip() for r in input("Which region(s) would you like to search? (separate multiple regions with commas): ").lower().split(',')]

    resources = get_resources_by_tag(tag_key, tag_value, regions)

    tf.header_print("\nResources queued for deletion:\n")
    resources_for_deletion = []

    for resource in resources:
        resource_for_deletion = parse_resource_by_type(resource)
        resources_for_deletion.append(resource_for_deletion)

    other_resources_for_deletion = get_other_resources(tag_key, tag_value, regions)
    resources_for_deletion.extend(other_resources_for_deletion)
    ordered_resources_for_deletion = order_resources_for_deletion(resources_for_deletion)
    print(json.dumps(ordered_resources_for_deletion, indent=4, default=str))

    print(f"\n{len(ordered_resources_for_deletion)} resources queued for deletion. \n")

    # Figure out how to make this clearer
    delete = input("Are you sure you want to delete all of these resources? (y/n): ")

    if delete.lower() != 'y':
        print("Exiting...")
        return

    prompt = input("Do you want to be prompted before deleting each resource? Selecting 'n' will delete all resources automatically. (y/n): ")
    print()

    failed_deletions = []

    for resource in ordered_resources_for_deletion:
        resource_name = resource.get('arn') or resource.get('resource_id')

        if prompt.lower() == 'y':
            confirm = input(f"\nDo you want to delete the following resource?\n{json.dumps(resource, indent=4, default=str )}\n[y/n]?: ")
            print()
            if confirm.lower() != 'y':
                print(f"Skipping deletion of {resource_name}")
                continue

        result = delete_resource(resource)

        if result:
            if isinstance(result, list):
                failed_deletions.extend(result)
            else:
                failed_deletions.append(result)

    if failed_deletions:
        retry_failed_deletions(failed_deletions)


if __name__ == '__main__':
    main()
