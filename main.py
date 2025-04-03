import json
import time
import boto3
import botocore.exceptions
from delete_functions import DELETE_FUNCTIONS


def get_resources_by_tag(tag_key, tag_value):
    '''' Gets list of resources by common tag key and value. '''
    client = boto3.client('resource-groups')

    query = {
        "Type": "TAG_FILTERS_1_0",
        "Query": json.dumps({
            "ResourceTypeFilters": ["AWS::AllSupported"],
            "TagFilters": [
                {
                    "Key": tag_key,
                    "Values": [tag_value]
                }
            ]
        })
    }

    resources = []
    response = client.search_resources(ResourceQuery=query)
    while True:
        resources.extend(response.get('ResourceIdentifiers', []))
        next_token = response.get('NextToken')

        if not next_token:
            break

        response = client.search_resources(ResourceQuery=query, NextToken=next_token)

    return resources


def parse_resource_by_type(resource):
    """Parses resource type, service and ARN from each resource to find the appropriate delete function."""
    arn = resource['ResourceArn']
    service = (resource['ResourceType'].split('::')[1]).lower()
    resource_type = (resource['ResourceType'].split('::')[2]).lower()
    resource_for_deletion = {
        'resource_type': resource_type,
        'arn': arn,
        'service': service
    }
    return resource_for_deletion


def order_resources_for_deletion(resources):


    networking_resources = [resource for resource in resources if "ec2" in resource["service"]]
    non_networking_resources = [resource for resource in resources if "ec2" not in resource["service"]]

    ordered_resources = []
    ordered_resources.extend([resource for resource in non_networking_resources])
    ordered_resources.extend([resource for resource in networking_resources if "vpcendpoint" in resource["resource_type"]])
    ordered_resources.extend([resource for resource in networking_resources if "natgateway" in resource["resource_type"]])
    ordered_resources.extend([resource for resource in networking_resources if "subnet" in resource["resource_type"]])
    ordered_resources.extend([resource for resource in networking_resources if "eip" in resource["resource_type"]])
    ordered_resources.extend([resource for resource in networking_resources if "routetable" in resource["resource_type"]])
    ordered_resources.extend([resource for resource in networking_resources if "internetgateway" in resource["resource_type"]])
    ordered_resources.extend([resource for resource in networking_resources if resource["resource_type"] == "vpc"])

    return ordered_resources



def delete_resource(resource):
    """Finds and calls the appropriate delete function based on the resource type."""
    service = resource['service']
    resource_type = resource['resource_type']
    arn = resource['arn']

    # print(f"DEBUG: Checking DELETE_FUNCTIONS for service='{service}', resource_type='{resource_type}'")

    if service in DELETE_FUNCTIONS and resource_type in DELETE_FUNCTIONS[service]:
        try:
            # print(f"DEBUG: Calling delete function for {service}::{resource_type}")
            DELETE_FUNCTIONS[service][resource_type](arn)

        except botocore.exceptions.ClientError as e:
            if "DependencyViolation" in str(e):
                return resource
            else:
                print(f"Failed to delete {arn}")
                return None

    else:
        print(f"No delete function found for {service}::{resource_type}")
        return None


def retry_failed_deletions(failed_resources, max_retries=6, wait_time=5):
    """Retries failed deletions up to max_retries times with exponential backoff."""

    for attempt in range(1, max_retries + 1):
        print(f"\nRetry attempt {attempt}/{max_retries} for failed deletions...\n")
        new_failed_resources = []

        for resource in failed_resources:
            if isinstance(resource, str):  # Skip if the resource is a string
                print(f"Skipping invalid resource: {resource}")
                continue

            try:
                result = delete_resource(resource)  # Returns failed resources if deletion still fails
                if result:
                    new_failed_resources.append(result)  # Collect still-failed resources
            except botocore.exceptions.ClientError as e:
                if "DependencyViolation" in str(e):
                    new_failed_resources.append(resource)
                else:
                    print(f"Failed to delete {resource['arn']}")

        if not new_failed_resources:  # If everything was deleted, exit early
            print("All failed deletions were successfully retried.")
            return

        # new_failed_resources.reverse()  # Reverse in place
        failed_resources = new_failed_resources  # Update failed resources
        print(f"{len(failed_resources)} resources still cannot be deleted. Retrying in {wait_time} seconds...")
        time.sleep(wait_time)  # Wait before retrying

    print(f"\nFinal retry attempt reached. {len(failed_resources)} resources could not be deleted.\n")


def main():
    tag_key = input("Enter the tag key to search by: ")
    tag_value = input("Enter the tag value to search by: ")
    resources = get_resources_by_tag(tag_key, tag_value)

    print("\n Resources queued for deletion: \n")
    resources_for_deletion = []

    for resource in resources:
        resource_for_deletion = parse_resource_by_type(resource)
        print(json.dumps(resource_for_deletion, indent=2))
        resources_for_deletion.append(resource_for_deletion)

    ordered_resources_for_deletion = order_resources_for_deletion(resources_for_deletion)

    print(f"\n{len(ordered_resources_for_deletion)} resources queued for deletion. \n")
    delete = input("Are you sure you want to delete all of these resources? (y/n): \n")

    if delete.lower() != 'y':
        print("Exiting...")
        return

    print("Deleting resources... \n")
    failed_deletions = []

    for resource in ordered_resources_for_deletion:
        failed_deletion = delete_resource(resource)
        if failed_deletion:
            failed_deletions.append(failed_deletion)

    if failed_deletions:
        print("\n Retrying failed deletions...")
        retry_failed_deletions(failed_deletions)


if __name__ == '__main__':
    main()
