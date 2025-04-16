"""Map services and resource types to appropriate delete function."""

from awsweepbytag import delete_functions as df

# fmt: off
DELETE_FUNCTIONS = {
    "apigateway": {
        "restapi": df.delete_rest_api,  # For REST APIs
    },
    "apigatewayv2": {
        "api": df.delete_api,  # For HTTP and websocket APIs
        "vpclink": df.delete_vpc_link,
    },
    "autoscaling": {
        "autoscalinggroup": df.delete_autoscaling_group,
    },
    "certificatemanager": {
        "certificate": lambda resource: print("deleting certificate"),  # delete_certificate(resource['arn'])
    },
    "cloudfront": {
        "distribution": df.delete_cloudfront_distribution,  # delete_distribution(resource['arn'])
    },
    "dynamodb": {
        "table": df.delete_dynamodb_table,
    },
    "ec2": {
        "ami": df.deregister_ami,
        "eip": df.release_eip,
        "instance": df.delete_ec2_instance,
        "internetgateway": df.delete_internet_gateway,
        "launchtemplate": df.delete_launch_template,
        "natgateway": df.delete_nat_gateway,
        "routetable": df.delete_route_table,
        "securitygroup": df.delete_security_group,
        "snapshot": df.delete_snapshot,
        "subnet": df.delete_subnet,
        "transitgatewayattachment": lambda resource: print("deleting transit gateway attachment"),  # delete_transit_gateway_vpc_attachment(resource['arn'])
        "vpc": df.delete_vpc,
        "vpcendpoint": df.delete_vpc_endpoint,
        "vpcpeering": lambda resource: print("deleting vpc peering"),  # delete_vpc_peering_connection(resource['arn'])
    },
    "elasticloadbalancingv2": {
        "loadbalancer": df.delete_elastic_load_balancer,
        "listener": df.delete_listener,
        "targetgroup": df.delete_target_group,
    },
    # "iam": {
    #     "managedpolicy": lambda resource: print("deleting managed policy"),  # delete_managed_policy(resource['arn'])
    #     "policy": lambda resource: print("deleting policy"),  # delete_policy(resource['arn'])
    #     "role": lambda resource: print("deleting role"),  # delete_role(resource['arn'])
    # },
    "kms": {
        "key": lambda resource: print("deleting key"),  # delete_key(resource['arn'])
    },
    "lambda": {
        "function": df.delete_lambda_function,
    },
    "rds": {
        "dbinstance": lambda resource: print("deleting db instance"),  # delete_db_instance(resource['arn'])
    },
    "route53": {
        "hostedzone": lambda resource: print("deleting hosted zone"),  # delete_hosted_zone(resource['arn'])
    },
    "s3": {
        "bucket": df.delete_s3_bucket,
    },
    "secretsmanager": {
        "secret": lambda resource: print("deleting secret"),  # delete_secret(resource['arn'])
    },
    "sns": {
        "topic": df.delete_sns_topic,
    },
    "sqs": {
        "queue": df.delete_sqs_queue,
    },
}
# fmt: on
