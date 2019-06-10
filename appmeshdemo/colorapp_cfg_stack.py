from aws_cdk import (aws_ecs as ecs, aws_appmesh as appmesh, aws_iam as iam, aws_servicediscovery as sdisc,
                     aws_ec2 as ec2, aws_elasticloadbalancingv2 as elbv2, cdk)
from utils import PolicyUtils as pu
from collections import namedtuple


class ColorappCfgStack(cdk.Stack):
    Props = namedtuple('Props', 'taskiamrole taskexeciamrole mesh environ repos colors cluster csg vpc')

    def __init__(self, app: cdk.App, id: str, cluster: ecs.Cluster, vpc: ec2.Vpc, mesh: appmesh.CfnMesh, repos: dict,
                 clustersg: ec2.SecurityGroup, publoadbal: elbv2.ApplicationLoadBalancer, **kwargs) -> None:
        super().__init__(app, id)

        env = pu.PolicyUtils.current_env(self)

        # TaskIamRole and TaskExecutionIamRole
        trole = iam.Role(self, 'TaskIamRole', assumed_by=iam.ServicePrincipal('ecs-tasks'),
                         managed_policy_arns=['arn:aws:iam::aws:policy/CloudWatchFullAccess',
                                              'arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess'])

        erole = iam.Role(self, 'TaskExecutionIamRole', assumed_by=iam.ServicePrincipal('ecs-tasks'),
                         managed_policy_arns=['arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly',
                                              'arn:aws:iam::aws:policy/CloudWatchLogsFullAccess'])

        props = self.Props(trole, erole, mesh, env, repos, ['white', 'red', 'blue', 'black'],
                           cluster, clustersg, vpc)
        apps = ['colorteller', 'gateway', 'tcpecho']

        tgroups = self.configure_load_balancers(props.vpc, publoadbal)

        virtnodes = {}
        for app in apps:
            virtnodes.update(self.configure_container(app, props, tgroups))

        vroute = appmesh.CfnVirtualRouter(self, 'colortellerVirtualRouter',
                                          virtual_router_name='colorteller-vr', mesh_name=props.mesh.mesh_name,
                                          spec={
                                              'listeners': [
                                                  {'portMapping': {'port': 9080, 'protocol': 'http'}}
                                              ]
                                          })

        route = appmesh.CfnRoute(self, 'colortellerRoute', mesh_name=props.mesh.mesh_name,
                                 route_name='colorteller-route', virtual_router_name='colorteller-vr',
                                 spec={'httpRoute': {
                                     'action': {
                                         'weightedTargets': [
                                             {'virtualNode': 'colorteller-white-vn', 'weight': 1},
                                             {'virtualNode': 'colorteller-red-vn', 'weight': 1},
                                             {'virtualNode': 'colorteller-blue-vn', 'weight': 1}
                                         ]
                                     },
                                     'match': {
                                         'prefix': '/'
                                     }
                                 }})

        appmesh.CfnVirtualService(self, id='colortellerVirtualService', mesh_name=props.mesh.mesh_name,
                                  virtual_service_name=repos['colorteller'].repository_name + '.' +
                                                       props.cluster.default_namespace.namespace_name,
                                  spec={'provider': {
                                      'virtualRouter': {'virtualRouterName': 'colorteller-vr'}
                                  }}).add_depends_on(vroute)

        appmesh.CfnVirtualService(self, id='tcpechoVirtualService', mesh_name=props.mesh.mesh_name,
                                  virtual_service_name='tcpecho.' +
                                                       props.cluster.default_namespace.namespace_name,
                                  spec={'provider': {
                                      'virtualNode': {'virtualNodeName': 'tcpecho--vn'}
                                  }}).add_depends_on(virtnodes['tcpecho'])

        route.add_depends_on(vroute)
        for virtnode in virtnodes:
            route.add_depends_on(virtnodes[virtnode])

    def configure_load_balancers(self, vpc: ec2.Vpc, publoadbal: elbv2.ApplicationLoadBalancer):
        tgroups = {}
        hc = elbv2.HealthCheck()
        hc['intervalSecs'] = 10
        hc['protocol'] = elbv2.ApplicationProtocol.Http
        hc['healthyThresholdCount'] = 10
        hc['unhealthyThresholdCount'] = 10
        hc['timeoutSeconds'] = 5
        hc['path'] = '/'

        targetgroups = [
            {'name': 'grafana', 'httpcode': '302', 'port': 3000},
            {'name': 'prometheus', 'httpcode': '405', 'port': 9090},
            {'name': 'colorgateway', 'httpcode': '200', 'port': 9080}]

        for tgs in targetgroups:
            tgname = tgs['name']
            code = tgs['httpcode']
            port = tgs['port']
            hc['healthyHttpCodes'] = code

            atg = elbv2.ApplicationTargetGroup(self, id=tgname + 'TargetGroup', protocol=elbv2.ApplicationProtocol.Http,
                                               port=port, deregistration_delay_sec=30, vpc=vpc,
                                               target_group_name='appmeshdemo-' + tgname + '-1', health_check=hc,
                                               target_type=elbv2.TargetType.Ip)

            lbl = elbv2.ApplicationListener(self, tgname + 'LoadBalancerListener', port=port,
                                            protocol=elbv2.ApplicationProtocol.Http, default_target_groups=[atg],
                                            load_balancer=publoadbal)

            elbv2.ApplicationListenerRule(self, tgname + 'LoadBalancerRule', listener=lbl,
                                          target_groups=[atg], priority=1, path_pattern='*')

            tgroups[tgname] = atg

        return tgroups

    def configure_container(self, appname: str, props: Props, tgroups: {}):
        virtnodes = {}
        if appname == 'gateway' or appname == 'tcpecho':
            colors = ['']
        else:
            colors = props.colors

        for color in colors:
            fullname = color.upper()+appname

            td = ecs.FargateTaskDefinition(self, fullname+'_task', cpu='256', memory_mi_b='512',
                                           execution_role=props.taskexeciamrole, task_role=props.taskiamrole)

            env = {}
            if appname != 'tcpecho':
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

            if appname != 'tcpecho':
                contimage = ecs.EcrImage.from_ecr_repository(props.repos[appname], tag='latest')
            else:
                contimage = ecs.ContainerImage.from_registry('cjimti/go-echo')

            port = 9080
            if appname == 'gateway':
                env['COLOR_TELLER_ENDPOINT'] = props.repos['colorteller'].repository_name +\
                                               '.'+props.cluster.default_namespace.namespace_name+':9080'
                env['TCP_ECHO_ENDPOINT'] = 'tcpecho.'+props.cluster.default_namespace.namespace_name+':2701'
            elif appname == 'colorteller':
                env['COLOR'] = color
            else:
                env = {'TCP_PORT': '2701', 'NODE_NAME': 'mesh/' + props.mesh.mesh_name + '/virtualNode/tcpecho--vn'}
                port = 2701

            cont = ecs.ContainerDefinition(self, fullname+'-container', task_definition=td, essential=True,
                                           logging=ecs.AwsLogDriver(self, fullname+'-logs', stream_prefix=fullname),
                                           image=contimage, environment=env)
            cont.add_port_mappings(container_port=port, host_port=port, protocol=ecs.Protocol.Tcp)

            # X-Ray and Envoy definition ----------------------------------------------------------------------------
            if appname != 'tcpecho':
                xrayimage = ecs.ContainerImage.from_registry('amazon/aws-xray-daemon')

                xtask = td.add_container('xray-daemon', image=xrayimage, cpu=32, memory_reservation_mi_b=256,
                                         logging=ecs.AwsLogDriver(self, fullname+'-xray-logs',
                                                                  stream_prefix=fullname+'-xray'),
                                         essential=True, user='1337')
                xtask.add_port_mappings(container_port=2000, host_port=2000, protocol=ecs.Protocol.Udp)

                # Envoy definition ----------------------------------------------------------------------------------
                ENVOY_IMAGE_LOC = '111345817488.dkr.ecr.us-west-2.amazonaws.com/aws-appmesh-envoy:v1.9.1.0-prod'
                envoyimage = ecs.EcrImage.from_registry(ENVOY_IMAGE_LOC)

                envoyenv = {
                    'APPMESH_VIRTUAL_NODE_NAME': 'mesh/'+props.mesh.mesh_name+'/virtualNode/'+appname+'-'+color+'-vn',
                    'ENABLE_ENVOY_XRAY_TRACING': '1',
                    'ENABLE_ENVOY_STATS_TAGS': '1',
                    'ENVOY_LOG_LEVEL': 'debug'
                }

                if appname == 'gateway':
                    envoyenv['APPMESH_VIRTUAL_NODE_NAME'] = 'mesh/'+props.mesh.mesh_name+'/virtualNode/gateway--vn'

                envoy_hc = ecs.HealthCheck()
                envoy_hc['command'] = ['CMD-SHELL',
                                       'curl -s http://localhost:9901/server_info | grep state | grep -q LIVE']
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

            # Prometheus & Grafana definition for Gateway ---------------------------------------------------------
            if appname == 'gateway':
                prometheusimage = ecs.EcrImage.from_ecr_repository(props.repos['prometheus'], tag='latest')

                ptask = td.add_container('prometheus', image=prometheusimage, essential=True,
                                         logging=ecs.AwsLogDriver(self, appname + '-prometheus-logs',
                                                                  stream_prefix=appname + '-prometheus'))
                ptask.add_port_mappings(container_port=9090, host_port=9090)

                grafanaimage = ecs.ContainerImage.from_registry('grafana/grafana:latest')
                gtask = td.add_container('grafana', image=grafanaimage, essential=True,
                                         logging=ecs.AwsLogDriver(self, appname + '-grafana-logs',
                                                                  stream_prefix=appname + '-grafana'))
                gtask.add_port_mappings(container_port=3000, host_port=3000)

            disco = ecs.ServiceDiscoveryOptions()
            disco['dnsRecordType'] = sdisc.DnsRecordType.A
            disco['dnsTtlSec'] = 3000
            if color == 'white':
                disco['name'] = 'colorteller'
            elif appname != 'gateway' and appname != 'tcpecho':
                disco['name'] = 'colorteller-'+color
            elif appname == 'gateway':
                disco['name'] = 'colorgateway'
            else:
                disco['name'] = 'tcpecho'

            svc = ecs.FargateService(self, fullname+'Service', maximum_percent=200, minimum_healthy_percent=100,
                                     desired_count=1, task_definition=td, cluster=props.cluster,
                                     vpc_subnets=props.vpc.private_subnets, security_group=props.csg,
                                     service_discovery_options=disco)

            if appname == 'gateway':
                svc._load_balancers = [{'containerName': 'grafana', 'containerPort': 3000,
                                        'targetGroupArn': tgroups['grafana'].target_group_arn}]

            path = '/ping' if appname != 'tcpecho' else '/'
            spec = {
                'listeners': [{
                    'portMapping': {'port': port, 'protocol': 'http'},
                    'healthCheck': {'protocol': 'http', 'path': path,
                                    'healthyThreshold': 2, 'unhealthyThreshold': 2,
                                    'timeoutMillis': 2000, 'intervalMillis': 5000}}],
                'serviceDiscovery': {
                    'dns': {'hostname': svc._cloudmap_service.service_name+'.'+
                                        props.cluster.default_namespace.namespace_name}
                }
            }

            if appname == 'gateway':
                spec['backends'] = [
                    {'virtualService': {'virtualServiceName':
                                            'colorteller'+'.'+props.cluster.default_namespace.namespace_name}},
                    {'virtualService': {'virtualServiceName':
                                            'tcpecho' + '.' + props.cluster.default_namespace.namespace_name}},
                ]

            # Create AppMesh virtual nodes ------------------------------------------------------------------------
            vn = appmesh.CfnVirtualNode(self, fullname + 'VirtualNode', mesh_name=props.mesh.mesh_name,
                                        virtual_node_name=appname + '-' + color + '-vn',
                                        spec=spec)

            virtnodes[fullname] = vn

        return virtnodes

