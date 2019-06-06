from aws_cdk import (aws_ecr as ecr, aws_iam as iam, aws_codebuild as codebuild, aws_codepipeline as pipeline,
                     aws_codepipeline_actions as pactions, aws_s3 as s3, aws_cloudformation as cfn, cdk)
from utils import PolicyUtils as pu
import requests
import json


class ColorappECRStack(cdk.Stack):
    _projects = []

    def __init__(self, app: cdk.App, id: str, apps: list, **kwargs) -> None:
        super().__init__(app, id)

        env = pu.PolicyUtils.current_env(self)
        uri = env['account']+'.dkr.ecr.'+env['region']+'.amazonaws.com'

        pd = pu.PolicyUtils.createpolicyfromfile('./appmeshdemo/policydocs/codedeployecr.json')
        cbrole = iam.Role(self, 'CodeBuildECRRole', assumed_by=iam.ServicePrincipal('codebuild'),
                          inline_policies={'codedeployecr': pd})

        pd = pu.PolicyUtils.createpolicyfromfile('./appmeshdemo/policydocs/codepipelinebuild.json')
        cprole = iam.Role(self, 'CodePipelineBuildRole', assumed_by=iam.ServicePrincipal('codepipeline'),
                          inline_policies={'codepipelinebuild': pd})

        # create the repositories
        for appl in apps:
            ecr.Repository(scope=self, id=id+appl, repository_name=appl)

            be = codebuild.BuildEnvironment()
            be['privileged'] = True
            be['buildImage'] = codebuild.LinuxBuildImage.UBUNTU_14_04_DOCKER_18_09_0

            be['environmentVariables'] = {'AWS_DEFAULT_REGION': codebuild.BuildEnvironmentVariable(value=env['region']),
                                          'AWS_ACCOUNT_ID': codebuild.BuildEnvironmentVariable(value=env['account']),
                                          'IMAGE_REPO_NAME': codebuild.BuildEnvironmentVariable(value=appl),
                                          'IMAGE_TAG': codebuild.BuildEnvironmentVariable(value='latest')}
            buildspec = {
                'version': '0.2',
                'phases': {
                    'install': {
                        'commands': ['echo install step']
                    },
                    'pre_build': {
                        'commands': ['echo logging in to AWS ECR...',
                                     '$(aws ecr get-login --no-include-email --region %s)' % env['region']]
                    },
                    'build': {
                        'commands': ['echo building Docker image...',
                                     'cd appmeshdemo/colorapp/%s' % appl,
                                     'docker build -t %s:latest .' % appl,
                                     'docker tag %s:latest %s/%s:latest' % (appl, uri, appl)]
                    },
                    'post_build': {
                        'commands': ['echo Docker image build complete!',
                                     'echo push latest Docker images to ECR...',
                                     'docker push %s/%s:latest' % (uri, appl)]
                    }
                }
            }

            proj = codebuild.Project(self, appl, environment=be, role=cbrole, build_spec=buildspec,
                                     source=codebuild.GitHubSource(repo='appmeshdemo', owner='fitzee'))

            self._projects.append(proj)

        cnt = 1
        for project in self._projects:
            call = cfn.AwsSdkCall()
            call['service'] = 'CodeBuild'
            call['action'] = 'startBuild'
            call['parameters'] = {'projectName': project.project_name}
            call['physicalResourceId'] = 'Custom%s' % project.project_name
            cfn.AwsCustomResource(self, 'CustomCodebuild%s' % cnt, on_create=call)
            cnt = cnt + 1
