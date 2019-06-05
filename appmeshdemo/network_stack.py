from ipaddress import ip_network
from aws_cdk import (aws_ec2 as ec2, cdk)


class NetworkStack(cdk.Stack):
    def __init__(self, app: cdk.App, id: str, **kwargs) -> None:
        super().__init__(app, id)

        vpc_cidr = ip_network('10.0.0.0/16')

        # create the VPC
        self._vpc = ec2.Vpc(self, id, cidr=str(vpc_cidr), max_a_zs=2, nat_gateways=2)

    @property
    def vpc(self):
        return self._vpc
