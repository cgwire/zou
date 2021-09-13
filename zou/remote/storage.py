from abc import ABCMeta, abstractmethod


class ObjectStorageClient(metaclass=ABCMeta):
    @abstractmethod
    def put(self, local_path, bucket, key):
        raise NotImplementedError

    @abstractmethod
    def get(self, bucket, key, local_path):
        raise NotImplementedError


class S3Client:
    def __init__(self, config):
        s3connection = dict(
            aws_access_key_id=config["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=config["AWS_SECRET_ACCESS_KEY"],
        )
        if config.get("AWS_DEFAULT_REGION"):
            s3connection["region_name"] = config.get("AWS_DEFAULT_REGION")
        if config.get("S3_ENDPOINT"):
            s3connection["endpoint_url"] = config.get("S3_ENDPOINT")

        import boto3

        self.s3client = boto3.client("s3", **s3connection)

    def get(self, bucket, key, local_fd):
        self.s3client.download_fileobj(bucket, key, local_fd)

    def put(self, local_path, bucket, key):
        self.s3client.upload_file(local_path, bucket, key)


class SwiftClient:
    def __init__(self, config):
        import swiftclient

        self.conn = swiftclient.Connection(
            authurl=config["OS_AUTH_URL"],
            user=config["OS_USERNAME"],
            key=config["OS_PASSWORD"],
            os_options={
                "region_name": config["OS_REGION_NAME"],
                "tenant_name": config["OS_TENANT_NAME"],
            },
            auth_version="3",
        )

    def get(self, bucket, key, local_fd):
        _, data = self.conn.get_object(bucket, key)
        local_fd.write(data)

    def put(self, local_path, bucket, key):
        with open(local_path, "rb") as local:
            self.conn.put_object(bucket, key, contents=local)
