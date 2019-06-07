from aws_cdk import (aws_appmesh as appmesh, cdk)


class AppMeshStack(cdk.Stack):
    def __init__(self, app: cdk.App, id: str, meshname: str, **kwargs) -> None:
        super().__init__(app, id)

        # create the AppMesh
        mesh = appmesh.CfnMesh(self, id, mesh_name=meshname)
        self._mesh = mesh

    @property
    def mesh(self):
        return self._mesh
