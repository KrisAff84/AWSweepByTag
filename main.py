import json

import botocore.exceptions

import get_and_order as go
import main_delete as md
import text_formatting as tf

VALID_REGIONS = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "af-south-1",
    "ap-east-1",
    "ap-south-1",
    "ap-south-2",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-southeast-3",
    "ap-southeast-4",
    "ap-southeast-5",
    "ap-southeast-7",
    "ap-northeast-1",
    "ap-northeast-2",
    "ap-northeast-3",
    "ca-central-1",
    "ca-west-1",
    "eu-central-1",
    "eu-central-2",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
    "eu-south-1",
    "eu-south-2",
    "eu-north-1",
    "il-central-1",
    "mx-central-1",
    "me-central-1",
    "me-south-1",
    "sa-east-1",
    "cn-north-1",
    "cn-northwest-1",
    "us-gov-east-1",
    "us-gov-west-1",
]


def main():
    tag_key = input("Enter the tag key to search by: ")
    tag_value = input("Enter the tag value to search by: ")
    regions = [
        r.strip() for r in input("Which region(s) would you like to search? (separate multiple regions with commas): ").lower().split(",")
    ]

    invalid_regions = []
    for region in regions:
        if region not in VALID_REGIONS:
            invalid_regions.append(region)

    if invalid_regions:
        tf.failure_print("\nThe following regions are invalid:\n")
        for region in invalid_regions:
            tf.indent_print(region)
        print()
        tf.subheader_print("Valid regions are:")
        for region in VALID_REGIONS:
            tf.indent_print(region)
        print("\nPlease try again with valid regions. Exiting...\n")
        return
    try:
        resources = go.get_resources_by_tag(tag_key, tag_value, regions)

    except (
        botocore.exceptions.NoCredentialsError,
        botocore.exceptions.PartialCredentialsError,
        botocore.exceptions.CredentialRetrievalError,
    ) as e:
        print()
        tf.failure_print("AWS credentials are missing or incomplete. Please check your setup and try again.")
        tf.indent_print(f"{e}\n", 8)
        tf.indent_print("Exiting...\n")
        return

    resources_for_deletion = []

    for resource in resources:
        resource_for_deletion = go.parse_resource_by_type(resource)
        resources_for_deletion.append(resource_for_deletion)

    other_resources_for_deletion = go.get_other_resources(tag_key, tag_value, regions)
    resources_for_deletion.extend(other_resources_for_deletion)
    ordered_resources_for_deletion = go.order_resources_for_deletion(resources_for_deletion)

    tf.header_print("\nResources queued for deletion:\n")

    print(json.dumps(ordered_resources_for_deletion, indent=4, default=str))
    print()

    if not ordered_resources_for_deletion:
        tf.header_print("No resources found to delete. Exiting...")
        return

    print(f"\n{len(ordered_resources_for_deletion)} resources queued for deletion. \n")

    # Figure out how to make this clearer
    delete = input("Are you sure you want to delete all of these resources? (y/n): ")

    if delete.lower() != "y":
        print("Exiting...")
        return

    prompt = input(
        "Do you want to be prompted before deleting each resource? Selecting 'n' will delete all resources automatically. (y/n): "
    )
    print()

    failed_deletions = []

    for resource in ordered_resources_for_deletion:
        resource_name = resource.get("arn") or resource.get("resource_id")

        if prompt.lower() == "y":
            confirm = input(f"\nDo you want to delete the following resource?\n{json.dumps(resource, indent=4, default=str )}\n[y/n]?: ")
            print()
            if confirm.lower() != "y":
                print(f"Skipping deletion of {resource_name}")
                continue

        result = md.delete_resource(resource)

        if result:
            if isinstance(result, list):
                failed_deletions.extend(result)
            else:
                failed_deletions.append(result)

    if failed_deletions:
        md.retry_failed_deletions(failed_deletions)

    else:
        print()
        tf.success_print("All resources were successfully deleted.\n", 0)


if __name__ == "__main__":
    main()
