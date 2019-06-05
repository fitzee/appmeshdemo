from aws_cdk import (aws_ecs as ecs, aws_ec2 as ec2, aws_iam as iam, aws_logs as logs, aws_servicediscovery as sd,
                     aws_elasticloadbalancingv2 as elbv2, cdk)
from utils import PolicyUtils as pu


class ContainerStack(cdk.Stack):
    def __init__(self, app: cdk.App, id: str, vpc: ec2.Vpc, servicedomain: str, **kwargs) -> None:
        super().__init__(app, id)

        cluster = ecs.Cluster(self, id, vpc=vpc)

        # ECSInstance role & profile
        pd = pu.PolicyUtils.createpolicyfromfile('./appmeshdemo/policydocs/ecs-service.json')
        ecsinstancerole = iam.Role(self, 'ECSInstanceRole', assumed_by=iam.ServicePrincipal('ec2'),
                                   inline_policies={'ecs-service': pd})
        iam.CfnInstanceProfile(self, 'ECSInstanceProfile', roles=[ecsinstancerole.role_name])

        # ECSServiceAutoScalingRole
        pd = pu.PolicyUtils.createpolicyfromfile('./appmeshdemo/policydocs/ecs-service-autoscaling.json')
        iam.Role(self, 'ECSServiceAutoScalingRole', assumed_by=iam.ServicePrincipal('application-autoscaling'),
                 inline_policies={'ecs-service-autoscaling': pd})

        # TaskIamRole and TaskExecutionIamRole
        iam.Role(self, 'TaskIamRole', assumed_by=iam.ServicePrincipal('ecs-tasks'),
                 managed_policy_arns=['arn:aws:iam::aws:policy/CloudWatchFullAccess',
                                      'arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess'])

        iam.Role(self, 'TaskExecutionIamRole', assumed_by=iam.ServicePrincipal('ecs-tasks'),
                 managed_policy_arns=['arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly',
                                      'arn:aws:iam::aws:policy/CloudWatchLogsFullAccess'])

        logs.LogGroup(self, 'ECSServiceLogGroup', retention_days=logs.RetentionDays.OneMonth)
        sd.PrivateDnsNamespace(self, 'ECSServiceDiscoveryNamespace', vpc=vpc, name=servicedomain)

        # Bastion host stuff -------------------------------------------------------------------------------------
        # BastionInstanceRole
        pd = pu.PolicyUtils.createpolicyfromfile('./appmeshdemo/policydocs/appmesh.json')
        bir = iam.Role(self, 'BastionInstanceRole', assumed_by=iam.ServicePrincipal('ec2'),
                       inline_policies={'appmesh': pd},
                       managed_policy_arns=['arn:aws:iam::aws:policy/service-role/AmazonEC2RoleforSSM'])
        bip = iam.CfnInstanceProfile(self, 'BastionInstanceProfile', roles=[bir.role_name])

        # Bastion EC2 instance
        bsg = ec2.SecurityGroup(self, 'BastionSG', vpc=vpc)
        bsg.add_ingress_rule(peer=ec2.AnyIPv4(), connection=ec2.TcpPortRange(0,65535))

        bhi = ec2.CfnInstance(self, 'BastionInstance', instance_type='t2.micro',
                              iam_instance_profile=bip.instance_profile_name,
                              image_id=ec2.AmazonLinuxImage().get_image(self).image_id,
                              subnet_id=vpc.private_subnets[0].subnet_id)
        # security_groups=[bsg.security_group_name],

        # Load-Balancer stuff ------------------------------------------------------------------------------------
        plbsg = ec2.SecurityGroup(self, 'PublicLoadBalancerSG', vpc=vpc)
        plbsg.add_ingress_rule(peer=ec2.AnyIPv4(), connection=ec2.TcpPortRange(0,65535))

        plb = elbv2.ApplicationLoadBalancer(self, 'PublicLoadBalancer', internet_facing=True,
                                            vpc_subnets=vpc.public_subnets,
                                            security_group=plbsg, vpc=vpc, idle_timeout_secs=30)

        healthchk = elbv2.HealthCheck()
        healthchk['intervalSecs'] = 6
        healthchk['healthyThresholdCount'] = 2
        healthchk['unhealthyThresholdCount'] = 2

        dtg = elbv2.ApplicationTargetGroup(self, 'DummyTargetGroupPublic', vpc=vpc, port=80,
                                           protocol=elbv2.ApplicationProtocol.Http,
                                           health_check=healthchk)

        plbl = elbv2.ApplicationListener(self, 'PublicLoadBalancerListener', load_balancer=plb, port=80,
                                         protocol=elbv2.ApplicationProtocol.Http,
                                         default_target_groups=[dtg])
