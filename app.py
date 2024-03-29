#!/usr/bin/env python3

from aws_cdk import cdk
from appmeshdemo.network_stack import NetworkStack
from appmeshdemo.container_stack import ContainerStack
from appmeshdemo.appmesh_stack import AppMeshStack
from appmeshdemo.colorapp_ecr_stack import ColorappECRStack
from appmeshdemo.colorapp_cfg_stack import ColorappCfgStack

sd = 'default.svc.cluster.local'
apps = ['colorteller', 'gateway', 'prometheus']
app = cdk.App()

ns = NetworkStack(app, 'appmeshdemo-network')
cs = ContainerStack(app, 'appmeshdemo-container', vpc=ns.vpc, servicedomain=sd)
cs.add_dependency(ns)
mesh = AppMeshStack(app, 'appmeshdemo-appmesh', 'default')
ecrs = ColorappECRStack(app, 'appmeshdemo-colorapp-ecr', apps=apps)
setup = ColorappCfgStack(app, 'appmeshdemo-colorapp-cfg', cluster=cs.cluster, vpc=ns.vpc, mesh=mesh.mesh,
                         repos=ecrs.repos, clustersg=cs.clustersg, publoadbal=cs.publoadbal)
app.run()
