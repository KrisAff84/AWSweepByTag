'''
Get IDs from resources that do not show up when using the 'resource-groups' client.

Most resources can be gathered using the 'resource-groups' client, but not all of them.
This file is used to get resource information needed for deletion that are not returned
from the 'resource-groups' client.

Functions:
    - get_images: Gathers AMIs and associated snapshots and returns them as a list of dicts.

'''

import boto3


def get_images(tag_key: str, tag_value: str, regions: list[str]) -> list[dict]:
    """
    Get all AMIs and associated snapshots for a given tag key and value in the specified regions.

    Args:
        tag_key (str): Tag key to search for resources by.
        tag_value (str): Tag value to search for resources by.
        regions (list[str]): List of regions to search for resources in.

    Returns:
        list[dict[str, str]] - List of dictionaries containing resource information.
            \nEach dictionary contains the following keys:
                - resource_type (str): The type of resource (ami or snapshot)
                - resource_id (str): The resource ID for each resource (AMI ID or Snapshot ID)
                - service (str): The service the resource belongs to (ec2)
                - region (str): Region where the resource is located.
    """
    resources = []
    for region in regions:
        client = boto3.client('ec2', region_name=region)
        response = client.describe_images(
            Owners=['self'],
            Filters=[
                {
                    'Name': f'tag:{tag_key}',
                    'Values': [tag_value]
                }
            ]
        )


        ami_ids = [image['ImageId'] for image in response['Images']]
        for ami in ami_ids:
            resources.append({
                "resource_type": "ami",
                "resource_id": ami,
                "service": "ec2",
                "region": region
            })

        for image in response['Images']:
            for mapping in image.get('BlockDeviceMappings', []):
                ebs = mapping.get('Ebs')
                if ebs and 'SnapshotId' in ebs:
                    resources.append({
                        "resource_type": "snapshot",
                        "resource_id": ebs['SnapshotId'],
                        "service": "ec2",
                        "region": region
                    })

    return resources
