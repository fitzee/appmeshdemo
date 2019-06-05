from aws_cdk import (aws_appmesh as appmesh, cdk)


class AppMeshStack(cdk.Stack):
    def __init__(self, app: cdk.App, id: str, meshname: str, **kwargs) -> None:
        super().__init__(app, id)

        # create the AppMesh
        appmesh.CfnMesh(self, id, mesh_name=meshname)
