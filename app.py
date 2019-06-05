#!/usr/bin/env python3

from aws_cdk import cdk

from appmeshdemo.network_stack import NetworkStack
from appmeshdemo.container_stack import ContainerStack
from appmeshdemo.appmesh_stack import AppMeshStack
from appmeshdemo.colorapp_ecr_stack import ColorappECRStack

apps = ['colorteller', 'gateway']
app = cdk.App()

ns = NetworkStack(app, 'appmeshdemo-network')
cs = ContainerStack(app, 'appmeshdemo-container', vpc=ns.vpc, servicedomain='default.svc.cluster.local')
cs.add_dependency(ns)
mesh = AppMeshStack(app, 'appmeshdemo-appmesh', 'default')
ecrs = ColorappECRStack(app, 'appmeshdemo-colorapp-ecr', apps=apps)

app.run()


