from aws_cdk import (aws_ecs as ecs, aws_ec2 as ec2, aws_iam as iam, aws_logs as logs, aws_servicediscovery as sd,
                     aws_elasticloadbalancingv2 as elbv2, cdk)
from utils import PolicyUtils as pu


class ContainerStack(cdk.Stack):
    def __init__(self, app: cdk.App, id: str, vpc: ec2.Vpc, servicedomain: str, **kwargs) -> None:
        super().__init__(app, id)

        cluster = ecs.Cluster(self, id, vpc=vpc)
        cluster.add_default_cloud_map_namespace(name=servicedomain, type=ecs.NamespaceType.PrivateDns)
        self._cluster = cluster

        ecssg = ec2.SecurityGroup(self, 'ECSServiceSecurityGroup', vpc=vpc)
        ecssg.add_ingress_rule(peer=ec2.CidrIPv4(vpc.vpc_cidr_block), connection=ec2.TcpAllPorts())
        self._clustersg = ecssg

        # Bastion host stuff -------------------------------------------------------------------------------------
        # BastionInstanceRole
        pd = pu.PolicyUtils.createpolicyfromfile('./appmeshdemo/policydocs/appmesh.json')
        bir = iam.Role(self, 'BastionInstanceRole', assumed_by=iam.ServicePrincipal('ec2'),
                       inline_policies={'appmesh': pd},
                       managed_policy_arns=['arn:aws:iam::aws:policy/service-role/AmazonEC2RoleforSSM'])
        bip = iam.CfnInstanceProfile(self, 'BastionInstanceProfile', roles=[bir.role_name])

        # Bastion EC2 instance
        bsg = ec2.SecurityGroup(self, 'BastionSG', vpc=vpc)
        bsg.add_ingress_rule(peer=ec2.AnyIPv4(), connection=ec2.TcpAllPorts())

        ni = ec2.CfnNetworkInterfaceProps()
        ni['associatePublicIpAddress'] =True
        ni['deviceIndex'] = '0'
        ni['groupSet'] = [bsg.security_group_name]
        ni['subnetId'] = vpc.public_subnets[0].subnet_id

        bhi = ec2.CfnInstance(self, 'BastionInstance', instance_type='t2.micro',
                              iam_instance_profile=bip.instance_profile_name,
                              image_id=ec2.AmazonLinuxImage().get_image(self).image_id,
                              network_interfaces=[ni])

        # Load-Balancer stuff ------------------------------------------------------------------------------------
        plbsg = ec2.SecurityGroup(self, 'PublicLoadBalancerSG', vpc=vpc)
        plbsg.add_ingress_rule(peer=ec2.AnyIPv4(), connection=ec2.TcpPortRange(0,65535))

        plb = elbv2.ApplicationLoadBalancer(self, 'PublicLoadBalancer', internet_facing=True,
                                            vpc_subnets=vpc.public_subnets,
                                            security_group=plbsg, vpc=vpc, idle_timeout_secs=30)
        self._publoadbal = plb

        healthchk = elbv2.HealthCheck()
        healthchk['intervalSecs'] = 6
        healthchk['healthyThresholdCount'] = 2
        healthchk['unhealthyThresholdCount'] = 2

        dtg = elbv2.ApplicationTargetGroup(self, 'DummyTargetGroupPublic', vpc=vpc, port=80,
                                           protocol=elbv2.ApplicationProtocol.Http,
                                           health_check=healthchk, target_group_name='appmeshdemo-drop-1')

        plbl = elbv2.ApplicationListener(self, 'PublicLoadBalancerListener', load_balancer=plb, port=80,
                                         protocol=elbv2.ApplicationProtocol.Http,
                                         default_target_groups=[dtg])

        cdk.CfnOutput(self, id='External URL', value='http://'+plb.load_balancer_dns_name)

    @property
    def cluster(self):
        return self._cluster

    @property
    def clustersg(self):
        return self._clustersg

    @property
    def publoadbal(self):
        return self._publoadbal
