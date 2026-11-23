import sys
import time
import boto3
from botocore.exceptions import ClientError
from sagemaker import image_uris

REGION = "us-east-1"
ENDPOINT_NAME = "recing-fm-endpoint"
ROLE_ARN = "arn:aws:iam::903797724117:role/service-role/AmazonSageMaker-ExecutionRole-20260921T093009"

sm = boto3.client("sagemaker", region_name=REGION)


def status():
    try:
        return sm.describe_endpoint(EndpointName=ENDPOINT_NAME)["EndpointStatus"]
    except ClientError:
        return None


def deploy(serverless=False):
    if status():
        print("El endpoint ya existe, estado:", status())
        return

    jobs = sm.list_training_jobs(SortBy="CreationTime", SortOrder="Descending",
                                 StatusEquals="Completed", MaxResults=1)
    job_name = jobs["TrainingJobSummaries"][0]["TrainingJobName"]
    model_data = sm.describe_training_job(TrainingJobName=job_name)["ModelArtifacts"]["S3ModelArtifacts"]
    print("Modelo:", model_data)

    model_name = f"{ENDPOINT_NAME}-{int(time.time())}"
    sm.create_model(
        ModelName=model_name,
        ExecutionRoleArn=ROLE_ARN,
        PrimaryContainer={
            "Image": image_uris.retrieve("factorization-machines", REGION),
            "ModelDataUrl": model_data,
        },
    )

    try:  # borra una config vieja con el mismo nombre, si quedó
        sm.delete_endpoint_config(EndpointConfigName=ENDPOINT_NAME)
    except ClientError:
        pass

    variant = {"VariantName": "AllTraffic", "ModelName": model_name}
    if serverless:
        variant["ServerlessConfig"] = {"MemorySizeInMB": 2048, "MaxConcurrency": 2}
    else:
        variant.update({"InstanceType": "ml.m5.large", "InitialInstanceCount": 1})

    sm.create_endpoint_config(EndpointConfigName=ENDPOINT_NAME, ProductionVariants=[variant])
    sm.create_endpoint(EndpointName=ENDPOINT_NAME, EndpointConfigName=ENDPOINT_NAME)

    print("Creando endpoint (puede tardar varios minutos)...")
    sm.get_waiter("endpoint_in_service").wait(
        EndpointName=ENDPOINT_NAME, WaiterConfig={"Delay": 30, "MaxAttempts": 40})
    print("Listo: InService.")
    if not serverless:
        print("RECUERDA: este endpoint cobra ~0.12 USD/hora. Bórralo con: python src\\endpoint.py delete")


def delete():
    for fn, kwargs in ((sm.delete_endpoint, {"EndpointName": ENDPOINT_NAME}),
                       (sm.delete_endpoint_config, {"EndpointConfigName": ENDPOINT_NAME})):
        try:
            fn(**kwargs)
        except ClientError as e:
            print("Aviso:", e.response["Error"]["Message"])
    print("Endpoint y configuración eliminados.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "deploy":
        deploy()
    elif cmd == "deploy-serverless":
        deploy(serverless=True)
    elif cmd == "delete":
        delete()
    else:
        print("Estado del endpoint:", status() or "no existe")