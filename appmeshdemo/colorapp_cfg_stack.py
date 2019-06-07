from aws_cdk import (aws_ecs as ecs, aws_appmesh as appmesh, aws_iam as iam, cdk)
from utils import PolicyUtils as pu
from collections import namedtuple


class ColorappCfgStack(cdk.Stack):
    Props = namedtuple('Props', 'servicedomain taskiamrole taskexeciamrole mesh environ repos colors')

    def __init__(self, app: cdk.App, id: str, servicedomain: str, mesh: appmesh.CfnMesh, repos: dict,
                 **kwargs) -> None:
        super().__init__(app, id)

        env = pu.PolicyUtils.current_env(self)

        # TaskIamRole and TaskExecutionIamRole
        trole = iam.Role(self, 'TaskIamRole', assumed_by=iam.ServicePrincipal('ecs-tasks'),
                         managed_policy_arns=['arn:aws:iam::aws:policy/CloudWatchFullAccess',
                                              'arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess'])

        erole = iam.Role(self, 'TaskExecutionIamRole', assumed_by=iam.ServicePrincipal('ecs-tasks'),
                         managed_policy_arns=['arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly',
                                              'arn:aws:iam::aws:policy/CloudWatchLogsFullAccess'])

        props = self.Props(servicedomain, trole, erole, mesh, env, repos, ['white', 'red', 'blue', 'black'])
        apps = ['colorteller', 'gateway']
        for app in apps:
            self.configure_container(app, props)

    def configure_container(self, appname: str, props: Props):
        if appname == 'gateway':
            colors = ['']
        else:
            colors = props.colors

        for color in colors:
            fullname = color.upper()+appname

            td = ecs.FargateTaskDefinition(self, fullname+'_task', cpu='256', memory_mi_b='512',
                                           execution_role=props.taskexeciamrole, task_role=props.taskiamrole)

            td.node.find_child('Resource').add_property_override('proxyConfiguration', {
                'type': 'APPMESH',
                'containerName': 'envoy',
                'proxyConfigurationProperties': [
                    {'name': 'IgnoredUID',
                     'value': '1337'},
                    {'name': 'ProxyIngressPort',
                     'value': '15000'},
                    {'name': 'ProxyEgressPort',
                     'value': '15001'},
                    {'name': 'AppPorts',
                     'value': '9080'},
                    {'name': 'EgressIgnoredIPs',
                     'value': '169.254.170.2,169.254.169.254'}
                ]
            })

            env = {
                'SERVER_PORT': '9080'
            }

            if appname == 'gateway':
                env['COLOR_TELLER_ENDPOINT'] = 'colorteller.'+props.servicedomain+':9080'
                env['TCP_ECHO_ENDPOINT'] = 'tcpecho.'+props.servicedomain+':2701'
            else:
                env['COLOR'] = color

            contimage = ecs.EcrImage.from_ecr_repository(props.repos[appname], tag='latest')
            cont = ecs.ContainerDefinition(self, fullname+'-container', task_definition=td, essential=True,
                                           logging=ecs.AwsLogDriver(self, fullname+'-logs', stream_prefix=fullname),
                                           image=contimage, environment=env)

            cont.add_port_mappings(container_port=9080, host_port=9080, protocol=ecs.Protocol.Tcp)

            # X-Ray definition --------------------------------------------------------------------------------------
            xrayimage = ecs.ContainerImage.from_registry('amazon/aws-xray-daemon')

            xtask = td.add_container('xray-daemon', image=xrayimage, cpu=32, memory_reservation_mi_b=256,
                                     logging=ecs.AwsLogDriver(self, fullname+'-xray-logs',
                                                              stream_prefix=fullname+'-xray'),
                                     essential=True, user='1337')
            xtask.add_port_mappings(container_port=2000, host_port=2000, protocol=ecs.Protocol.Udp)

            # Envoy definition --------------------------------------------------------------------------------------
            ENVOY_IMAGE_LOC = '111345817488.dkr.ecr.us-west-2.amazonaws.com/aws-appmesh-envoy:v1.9.1.0-prod'
            envoyimage = ecs.EcrImage.from_registry(ENVOY_IMAGE_LOC)

            envoyenv = {
                'APPMESH_VIRTUAL_NODE_NAME': props.mesh.mesh_name+'/virtualNode/'+appname+'-'+color+'-vn',
                'ENABLE_ENVOY_XRAY_TRACING': '1',
                'ENABLE_ENVOY_STATS_TAGS': '1',
                'ENVOY_LOG_LEVEL': 'debug'
            }

            envoy_hc = ecs.HealthCheck()
            envoy_hc['command'] = ['CMD-SHELL', 'curl -s http://localhost:9901/server_info | grep state | grep -q LIVE']
            envoy_hc['interval'] = 5
            envoy_hc['timeout'] = 2
            envoy_hc['retries'] = 3

            etask = td.add_container('envoy', image=envoyimage, user='1337', essential=True, environment=envoyenv,
                                     logging=ecs.AwsLogDriver(self, fullname+'-envoy-logs',
                                                              stream_prefix=fullname+'-envoy'),
                                     health_check=envoy_hc)
            etask.add_port_mappings(container_port=9901, host_port=9901, protocol=ecs.Protocol.Tcp)
            etask.add_port_mappings(container_port=15000, host_port=15000, protocol=ecs.Protocol.Tcp)
            etask.add_port_mappings(container_port=15001, host_port=15001, protocol=ecs.Protocol.Tcp)

        # Prometheus & Grafana definition -------------------------------------------------------------------------
        if appname == 'gateway':
            prometheusimage = ecs.EcrImage.from_ecr_repository(props.repos[appname], tag='latest')

            ptask = td.add_container('prometheus', image=prometheusimage, essential=True,
                                     logging=ecs.AwsLogDriver(self, appname + '-prometheus-logs',
                                                              stream_prefix=appname + '-prometheus'))
            ptask.add_port_mappings(container_port=9090, host_port=9090)

            grafanaimage = ecs.ContainerImage.from_registry('grafana/grafana:latest')
            gtask = td.add_container('grafana', image=grafanaimage, essential=True,
                                     logging=ecs.AwsLogDriver(self, appname + '-grafana-logs',
                                                              stream_prefix=appname + '-grafana'))
            gtask.add_port_mappings(container_port=3000, host_port=3000)
