from aws_cdk import (aws_ecr as ecr, aws_iam as iam, aws_codebuild as codebuild, cdk)
from utils import PolicyUtils as pu
import docker


class ColorappECRStack(cdk.Stack):
    def __init__(self, app: cdk.App, id: str, apps: list, **kwargs) -> None:
        super().__init__(app, id)

        env = pu.PolicyUtils.current_env(self)
        uri = env['account']+'.dkr.ecr.'+env['region']+'.amazonaws.com/'
        docker_client = docker.from_env()

        # create the repositories
        for appl in apps:
            ecr.Repository(scope=self, id=id+appl, repository_name=appl)
            #print('./appmeshdemo/colorapp/'+appl)
            #img = docker_client.images.build(path='./appmeshdemo/colorapp/'+appl, tag=uri+appl.lower())
            #docker_client.images.push(repository=uri+appl.lower())

            be = codebuild.BuildEnvironment()
            be['privileged'] = True
            be['buildImage'] = codebuild.LinuxBuildImage.UBUNTU_14_04_DOCKER_18_09_0

            be['environmentVariables'] = {'AWS_DEFAULT_REGION': codebuild.BuildEnvironmentVariable(value=env['region']),
                                          'AWS_ACCOUNT_ID': codebuild.BuildEnvironmentVariable(value=env['account']),
                                          'IMAGE_REPO_NAME': codebuild.BuildEnvironmentVariable(value=appl),
                                          'IMAGE_TAG': codebuild.BuildEnvironmentVariable(value='latest')}
            #
            # benv = {'AWS_DEFAULT_REGION': codebuild.BuildEnvironmentVariable(env['region']),
            #         'AWS_ACCOUNT_ID': codebuild.BuildEnvironmentVariable(env['account']),
            #         'IMAGE_TAG':  codebuild.BuildEnvironmentVariable('latest')}

            buildspec = {
                'version': '0.2',
                'phases': {
                    'install': {
                        'commands': ['echo install step']
                    },
                    'pre_build': {
                        'commands': ['echo logging in to AWS ECR...',
                                     '$(aws ecr get-login --no-include-email --region us-east-1)']
                    },
                    'build': {
                        'commands': ['echo build Docker image on `date`',
                                     'cd src',
                                     'docker build -t sample-express-app:latest .',
                                     'docker tag sample-express-app:latest <your-ecr-url>/sample-express-app:latest']
                    },
                    'post_build': {
                        'commands': ['echo build Docker image complete `date`',
                                     'echo push latest Docker images to ECR...',
                                     'docker push <your-ecr-url>/sample-express-app:latest']
                    }
                }
            }

            pd = pu.PolicyUtils.createpolicyfromfile('./appmeshdemo/policydocs/codedeployecr.json')
            cbrole = iam.Role(self, 'CodeBuildECRRole', assumed_by=iam.ServicePrincipal('codebuild'),
                              inline_policies={'codedeployecr': pd})

            cb = codebuild.Project(self, id, environment=be, role=cbrole, build_spec=buildspec)
