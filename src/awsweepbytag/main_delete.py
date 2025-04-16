import json
import time

import botocore.exceptions

from awsweepbytag import delete_resource_map as drmap
from awsweepbytag import text_formatting as tf
from awsweepbytag.delete_functions import (
    delete_cloudfront_distribution,
    disable_cloudfront_distribution,
    wait_for_distribution_disabled,
)


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

    service = resource["service"]
    resource_type = resource["resource_type"]
    arn = resource.get("arn") or resource.get("resource_id")
    region = resource["region"]

    # print(f"DEBUG: Checking DELETE_FUNCTIONS for service='{service}', resource_type='{resource_type}'")

    # CloudFront distributions are handled differently than other resources since disabling them can take several minutes.
    # The disable_cloudfront_distribution will attempt to delete if it is already disabled, otherwise it will return retry = True
    # which allows it to be retried later.
    if resource_type == "distribution":
        retry = disable_cloudfront_distribution(arn)  # type: ignore
        if retry:
            return [resource]
        else:
            return None

    if service in drmap.DELETE_FUNCTIONS and resource_type in drmap.DELETE_FUNCTIONS[service]:  # type: ignore
        try:
            resources = drmap.DELETE_FUNCTIONS[service][resource_type](arn, region)  # type: ignore
            if resources:
                return resources
            else:
                return None

        except botocore.exceptions.ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")

            # These exceptions will not be handled by the retry function since they indicate the resource does not exist
            if error_code in [
                "NotFoundException",
                "NoSuchEntity",
                "ResourceNotFoundException",
            ]:
                tf.indent_print(f"Resource '{arn}' not found. It may have already been deleted. Skipping...")
                return None

            # These exceptions will be handled by the retry function
            if error_code in [
                "DependencyViolation",
                "TooManyRequestsException",
                "ThrottlingException",
                "ServiceUnavailableException",
            ]:
                tf.failure_print(f"Resource '{arn}' could not be deleted due to a {error_code}. Retrying later...")
                return [resource]  # Return to main function for retry

            # Unknown exceptions to be handled by retry function for good measure
            tf.failure_print(f"Resource '{arn}' could not be deleted. Error:\n")
            error_message_lines = str(e).split(": ", 1)
            tf.failure_print(error_message_lines[0])
            tf.failure_print(error_message_lines[1])
            print()
            tf.indent_print("Retrying later...\n")
            return [resource]

    else:
        tf.header_print(f"No delete function found for {service}::{resource_type}. Resource must be deleted manually\n")
        return None


# Need to print a statement when all resources have been deleted
def retry_failed_deletions(failed_resources: list[dict[str, str]], max_retries: int = 6, wait_time: int = 10) -> None:
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
            wait_for_distribution_disabled(resource["arn"])
            delete_cloudfront_distribution(resource["arn"])
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
                    new_failed_resources.extend(result)

            except botocore.exceptions.ClientError as e:
                if "DependencyViolation" in str(e):
                    new_failed_resources.extend([resource])
                else:
                    tf.failure_print(
                        f"Fail from retry function: Failed to delete {resource['arn']}",
                        0,
                    )

        if not new_failed_resources:
            tf.success_print("All resources were successfully deleted.", 0)
            return

        other_resources = new_failed_resources
        print(f"{len(other_resources)} resources still cannot be deleted. Retrying in {wait_time} seconds...\n")
        time.sleep(wait_time)

    if other_resources:
        tf.failure_print(
            f"\nFinal retry attempt reached. {len(other_resources)} resources could not be deleted.",
            0,
        )
        print("Resources that could not be deleted:\n")
        for resource in other_resources:
            tf.response_print(json.dumps(resource, indent=4, default=str), 4)
