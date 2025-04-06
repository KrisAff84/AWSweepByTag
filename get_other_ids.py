# import json
import boto3


def get_images(tag_key, tag_value):
    client = boto3.client('ec2')
    response = client.describe_images(
        Owners=['self'],
        Filters=[
            {
                'Name': f'tag:{tag_key}',
                'Values': [tag_value]
            }
        ]
    )

    resources = []

    ami_ids = [image['ImageId'] for image in response['Images']]
    for ami in ami_ids:
        resources.append({
            "resource_type": "ami",
            "resource_id": ami,
            "service": "ec2",
        })

    for image in response['Images']:
        for mapping in image.get('BlockDeviceMappings', []):
            ebs = mapping.get('Ebs')
            if ebs and 'SnapshotId' in ebs:
                resources.append({
                    "resource_type": "snapshot",
                    "resource_id": ebs['SnapshotId'],
                    "service": "ec2",
                })

    # print(json.dumps(resources, indent=4, default=str))
    return resources

def main():
    get_images('delete', 'true')


if __name__ == '__main__':
    main()