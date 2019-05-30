#!/usr/bin/env python3

from aws_cdk import cdk

from chekin.chekin_stack import ChekinStack


app = cdk.App()
ChekinStack(app, "chekin-cdk-1")

app.run()
