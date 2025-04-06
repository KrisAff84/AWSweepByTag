import json
import time
import boto3
import botocore.exceptions
from delete_functions import DELETE_FUNCTIONS, disable_cloudfront_distribution, wait_for_distribution_disabled, delete_cloudfront_distribution
import get_other_ids


def get_resources_by_tag(tag_key, tag_value):
    '''' Gets list of resources by common tag key and value. '''
    client = boto3.client('resource-groups')

    query = {
        "Type": "TAG_FILTERS_1_0",
        "Query": json.dumps({
            "ResourceTypeFilters": [
                "AWS::AllSupported",
            ],
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

    asgclient = boto3.client('autoscaling')
    autoscaling_groups = asgclient.describe_auto_scaling_groups(
        Filters=[
            {
                'Name': 'tag:{}'.format(tag_key),
                'Values': [tag_value]
            }
        ]
    )

    for asg in autoscaling_groups.get("AutoScalingGroups", []):
        asg_arn = asg["AutoScalingGroupARN"]
        resource = {
            "ResourceArn": asg_arn,
            "ResourceType": "AWS::AutoScaling::AutoScalingGroup",
        }
        resources.append(resource)
    return resources


def get_other_resources(tag_key, tag_value):
    '''
    Gets other resources that are not present when using the 'resource-groups' client.
    '''

    resources = []
    images_and_snapshots = get_other_ids.get_images(tag_key, tag_value)
    resources.extend(images_and_snapshots)

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
    # Networking resources that must follow a particular deletion order
    networking_resources = [resource for resource in resources if "ec2" in resource["service"]]
    # Other resources that must follow a particlar deletion order
    ordered_non_networking_resources = [resource for resource in resources if "ec2" not in resource["service"]]
    non_ordered_resources = [resource for resource in ordered_non_networking_resources if resource["service"] not in ["elasticloadbalancingv2", "autoscaling"]]
    other_resources = [resource for resource in resources if resource.get("resource_id")]

    ordered_resources = []
    ordered_resources.extend([resource for resource in non_ordered_resources])
    ordered_resources.extend([resource for resource in other_resources])
    ordered_resources.extend([resource for resource in ordered_non_networking_resources if "autoscaling" in resource["service"]])
    ordered_resources.extend([resource for resource in ordered_non_networking_resources if "elasticloadbalancingv2" in resource["service"]])
    ordered_resources.extend([resource for resource in networking_resources if "instance" in resource["resource_type"]])
    ordered_resources.extend([resource for resource in networking_resources if "vpcendpoint" in resource["resource_type"]])
    ordered_resources.extend([resource for resource in networking_resources if "natgateway" in resource["resource_type"]])
    ordered_resources.extend([resource for resource in networking_resources if "subnet" in resource["resource_type"]])
    ordered_resources.extend([resource for resource in networking_resources if "eip" in resource["resource_type"]])
    ordered_resources.extend([resource for resource in networking_resources if "internetgateway" in resource["resource_type"]])
    ordered_resources.extend([resource for resource in networking_resources if "routetable" in resource["resource_type"]])
    ordered_resources.extend([resource for resource in networking_resources if resource["resource_type"] == "vpc"])

    return ordered_resources


def delete_resource(resource):
    """Finds and calls the appropriate delete function based on the resource type."""
    service = resource['service']
    resource_type = resource['resource_type']
    arn = resource.get('arn') or resource.get('resource_id')

    # print(f"DEBUG: Checking DELETE_FUNCTIONS for service='{service}', resource_type='{resource_type}'")

    if resource_type == "distribution":
        retry = disable_cloudfront_distribution(arn)
        if retry:
            return resource
        else:
            return

    if service in DELETE_FUNCTIONS and resource_type in DELETE_FUNCTIONS[service]:
        try:
            # print(f"DEBUG: Calling delete function for {service}::{resource_type}")
            DELETE_FUNCTIONS[service][resource_type](arn)

        except botocore.exceptions.ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')

            if error_code == "DependencyViolation":
                print(f"DEBUG: Dependency violation detected for {arn}, retrying later...")
                return resource  # Now it will be retried

            print(f"Failed to delete {arn}, error: {e}")
            return None

    else:
        print(f"No delete function found for {service}::{resource_type}. Resource must be deleted manually")
        return None

# Need to print a statement when all resources have been deleted
def retry_failed_deletions(failed_resources, max_retries=6, wait_time=5):
    """Retries failed deletions up to max_retries times with exponential backoff."""
    # Separate CloudFront distributions from other resources
    cloudfront_resources = [r for r in failed_resources if r.get("resource_type") == "distribution"]
    other_resources = [r for r in failed_resources if r.get("resource_type") != "distribution"]

    # Handle CloudFronts first
    for resource in cloudfront_resources:
        try:
            wait_for_distribution_disabled(resource['arn'])
            delete_cloudfront_distribution(resource['arn'])
        except Exception as e:
            print(f"Error deleting CloudFront distribution {resource['arn']} on retry: {str(e)}")
            other_resources.append(resource)  # Add it back for retry if it still fails

    if other_resources == []:
        return

    # Retry loop for everything else
    for attempt in range(1, max_retries + 1):
        print(f"\nRetry attempt {attempt}/{max_retries} for failed deletions...\n")
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
                    print(f"Fail from retry function: Failed to delete {resource['arn']}")

        if not new_failed_resources:
            print("All resources were successfully deleted.")
            return

        other_resources = new_failed_resources
        print(f"{len(other_resources)} resources still cannot be deleted. Retrying in {wait_time} seconds...")
        time.sleep(wait_time)

    if other_resources:
        print(f"\nFinal retry attempt reached. {len(other_resources)} resources could not be deleted.\n")


def main():
    tag_key = input("Enter the tag key to search by: ")
    tag_value = input("Enter the tag value to search by: ")
    resources = get_resources_by_tag(tag_key, tag_value)

    print("\n Resources queued for deletion: \n")
    resources_for_deletion = []

    for resource in resources:
        resource_for_deletion = parse_resource_by_type(resource)
        resources_for_deletion.append(resource_for_deletion)

    other_resources_for_deletion = get_other_resources(tag_key, tag_value)
    resources_for_deletion.extend(other_resources_for_deletion)
    ordered_resources_for_deletion = order_resources_for_deletion(resources_for_deletion)
    print(json.dumps(ordered_resources_for_deletion, indent=4, default=str))

    print(f"\n{len(ordered_resources_for_deletion)} resources queued for deletion. \n")

    # Figure out how to make this clearer
    delete = input("Are you sure you want to delete all of these resources? (y/n): \n")
    prompt = input("Do you want to be prompted before deleting each resource? Selecting 'n' will delete all resources automatically. (y/n): \n")

    if delete.lower() != 'y':
        print("Exiting...")
        return

    failed_deletions = []

    for resource in ordered_resources_for_deletion:
        resource_name = resource.get('arn') or resource.get('resource_id')

        if prompt.lower() == 'y':
            confirm = input(f"\nDo you want to delete the following resource?\n{json.dumps(resource, indent=4, default=str )}\n[y/n]?: ")
            if confirm.lower() != 'y':
                print(f"Skipping deletion of {resource_name}")
                continue

        failed_deletion = delete_resource(resource)
        if failed_deletion:
            failed_deletions.append(failed_deletion)

    if failed_deletions:
        retry_failed_deletions(failed_deletions)


if __name__ == '__main__':
    main()
