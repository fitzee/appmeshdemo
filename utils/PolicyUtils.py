from aws_cdk import (aws_iam as iam, cdk)
import json


class PolicyUtils:
    def __init__(self) -> None:
        super().__init__(self)

    @staticmethod
    def createpolicyfromfile(policyfile, policyresource='*'):
        policydocument = iam.PolicyDocument()

        with open(policyfile, 'r') as fp:
            policydict = json.load(fp)
            fp.close()

        for statement in policydict['Statement']:
            ps = iam.PolicyStatement()
            ps.add_resource(policyresource)
            for action in statement['Action']:
                ps.add_action(action)

            policydocument.add_statement(ps)

        return policydocument

    @staticmethod
    def current_env(construct: cdk.Construct) -> cdk.Environment:
        env = cdk.Environment()
        # env['account'] = construct.node.get_context('aws:cdk:toolkit:default-account')
        env['account'] = construct.node.get_context('aws:cdk:toolkit:default-account')
        # env['region'] = construct.node.get_context('aws:cdk:toolkit:default-region')
        env['region'] = construct.node.get_context('aws:cdk:toolkit:default-region')
        return env

