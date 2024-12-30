import boto3
import time
import logging
import json
import botocore

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_stack_arn(stack_name):
    cfn_client = boto3.client('cloudformation')
    try:
        response = cfn_client.describe_stacks(StackName=stack_name)
        return response['Stacks'][0]['StackId']
    except botocore.exceptions.ClientError as e:
        logger.error(f"Error getting stack ARN: {e.response['Error']['Message']}")
        raise

def handler(event, context):
    logger.info(f"Received event: {event}")
    if event['RequestType'] in ['Create', 'Update']:
        try:
            resilience_hub = boto3.client('resiliencehub')
            
            app_arn = event['ResourceProperties']['AppArn']
            stack_name = event['ResourceProperties']['SourceStackName']
            
            # Get the stack ARN
            stack_arn = get_stack_arn(stack_name)
            logger.info(f"Retrieved stack ARN: {stack_arn}")
            
            # Import resources to draft app version
            logger.info(f"Importing resources from stack {stack_arn} to app {app_arn}")
            try:
                import_response = resilience_hub.import_resources_to_draft_app_version(
                    appArn=app_arn,
                    sourceArns=[stack_arn]
                )
                logger.info(f"Import response: {json.dumps(import_response, default=str)}")
            except botocore.exceptions.ClientError as e:
                logger.error(f"Error during import: {e.response['Error']['Message']}")
                raise

            # Wait for import to complete
            for i in range(20):  # Wait up to 10 minutes
                logger.info(f"Checking import status (attempt {i+1})")
                try:
                    status_response = resilience_hub.describe_draft_app_version_resources_import_status(appArn=app_arn)
                    logger.info(f"Import status response: {json.dumps(status_response, default=str)}")
                    
                    status = status_response.get('status')
                    if status == 'Success':
                        logger.info("Import completed successfully")
                        break
                    elif status == 'Failed':
                        logger.error("Import failed")
                        raise Exception('Import failed')
                    elif status in ['Pending', 'InProgress']:
                        if i == 19:  # Last iteration
                            logger.error("Import timed out")
                            raise Exception('Import timed out')
                        time.sleep(30)
                    else:
                        logger.error(f"Unknown import status: {status}")
                        raise Exception(f'Unknown import status: {status}')
                except botocore.exceptions.ClientError as e:
                    logger.error(f"Error checking import status: {e.response['Error']['Message']}")
                    raise

            # Resolve resources
            logger.info("Resolving resources")
            try:
                resolve_response = resilience_hub.resolve_app_version_resources(
                    appArn=app_arn,
                    appVersion='draft'
                )
                logger.info(f"Resolve response: {json.dumps(resolve_response, default=str)}")
            except botocore.exceptions.ClientError as e:
                logger.error(f"Error resolving resources: {e.response['Error']['Message']}")
                raise

            # Wait for resolution to complete
            for i in range(20):  # Wait up to 10 minutes
                logger.info(f"Checking resolution status (attempt {i+1})")
                try:
                    status_response = resilience_hub.describe_app_version_resources_resolution_status(
                        appArn=app_arn,
                        appVersion='draft'
                    )
                    logger.info(f"Resolution status response: {json.dumps(status_response, default=str)}")
                    
                    status = status_response.get('status')
                    if status == 'Success':
                        logger.info("Resolution completed successfully")
                        break
                    elif status == 'Failed':
                        logger.error("Resolution failed")
                        raise Exception('Resolution failed')
                    elif status in ['Pending', 'InProgress']:
                        if i == 19:  # Last iteration
                            logger.error("Resolution timed out")
                            raise Exception('Resolution timed out')
                        time.sleep(30)
                    else:
                        logger.error(f"Unknown resolution status: {status}")
                        raise Exception(f'Unknown resolution status: {status}')
                except botocore.exceptions.ClientError as e:
                    logger.error(f"Error checking resolution status: {e.response['Error']['Message']}")
                    raise

            # List resources in the app version
            try:
                list_response = resilience_hub.list_app_version_resources(
                    appArn=app_arn,
                    appVersion='draft'
                )
                logger.info(f"List resources response: {json.dumps(list_response, default=str)}")
                
                resources = list_response.get('physicalResources', [])
                if not resources:
                    logger.warning("No resources found in the app after import")
                else:
                    logger.info(f"Found {len(resources)} resources in the app")
            except botocore.exceptions.ClientError as e:
                logger.error(f"Error listing resources: {e.response['Error']['Message']}")
                raise

            return {'PhysicalResourceId': 'ImportResources', 'Status': 'SUCCESS'}
        except Exception as e:
            logger.error(f"An error occurred: {str(e)}")
            return {
                'PhysicalResourceId': 'ImportResources',
                'Status': 'FAILED',
                'Reason': str(e)
            }
    else:
        logger.info("No action required for Delete event")
        return {'PhysicalResourceId': 'ImportResources', 'Status': 'SUCCESS'}