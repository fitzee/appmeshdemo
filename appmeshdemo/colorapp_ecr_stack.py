from aws_cdk import (aws_ecr as ecr, aws_iam as iam, aws_codebuild as codebuild, aws_cloudformation as cfn, cdk)
from utils import PolicyUtils as pu


class ColorappECRStack(cdk.Stack):
    def __init__(self, app: cdk.App, id: str, apps: list, **kwargs) -> None:
        super().__init__(app, id)

        env = pu.PolicyUtils.current_env(self)
        uri = env['account']+'.dkr.ecr.'+env['region']+'.amazonaws.com'

        pd = pu.PolicyUtils.createpolicyfromfile('./appmeshdemo/policydocs/codedeployecr.json')
        cbrole = iam.Role(self, 'CodeBuildECRRole', assumed_by=iam.ServicePrincipal('codebuild'),
                          inline_policies={'codedeployecr': pd})

        # create the repositories
        cnt = 1
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

            # Create the build project in CodeBuild
            proj = codebuild.Project(self, appl, environment=be, role=cbrole, build_spec=buildspec,
                                     source=codebuild.GitHubSource(repo='appmeshdemo', owner='fitzee'))

            # Create a custom CloudFormation resource to start the build
            call = cfn.AwsSdkCall()
            call['service'] = 'CodeBuild'
            call['action'] = 'startBuild'
            call['parameters'] = {'projectName': proj.project_name}
            call['physicalResourceId'] = 'Custom%s' % proj.project_name
            cfn.AwsCustomResource(self, 'CustomCodebuild%s' % cnt, on_create=call, on_update=call)
            cnt = cnt + 1
