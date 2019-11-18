# Third Party
import boto3
import environ

env = environ.Env()


class AwsPubsub:
    def __init__(self):

        self.arn_prefix = env.str("AWS_ARN_PREFIX")
        self.sns = boto3.client("sns")

    def topic_path(self, _namespace, name):
        return f"{self.arn_prefix}:{name}"

    def publish(self, topic_path, data):
        self.sns.publish(TopicArn=topic_path, Message=data.decode("utf8"))


publisher = AwsPubsub()
