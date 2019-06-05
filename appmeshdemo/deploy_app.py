buildspec = {
    'version': '0.2',
    'phases': {
        'install': {
            'commands': ['echo install step']
        },
        'pre_build': {
            'commands': ['echo logging in to AWS ECR...',
                         '$(aws ecr get-login --no-include-email --region us-east-1']
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
