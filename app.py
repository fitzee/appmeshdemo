#!/usr/bin/env python3

from aws_cdk import cdk
from appmeshdemo.network_stack import NetworkStack
from appmeshdemo.container_stack import ContainerStack
from appmeshdemo.appmesh_stack import AppMeshStack
from appmeshdemo.colorapp_ecr_stack import ColorappECRStack
from appmeshdemo.colorapp_cfg_stack import ColorappCfgStack


apps = ['colorteller', 'gateway', 'prometheus']
app = cdk.App()

ns = NetworkStack(app, 'appmeshdemo-network')
cs = ContainerStack(app, 'appmeshdemo-container', vpc=ns.vpc, servicedomain='default.svc.cluster.local')
cs.add_dependency(ns)
mesh = AppMeshStack(app, 'appmeshdemo-appmesh', 'default')
ecrs = ColorappECRStack(app, 'appmeshdemo-colorapp-ecr', apps=apps)
setup = ColorappCfgStack(app, 'appmeshdemo-colorapp-cfg', mesh=mesh.mesh, repos=ecrs.repos, apps=apps)
app.run()
