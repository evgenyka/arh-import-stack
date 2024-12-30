import boto3
import json
import logging
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

RETRIES = 20
DELAY = 30

# Helper function to retrieve the CloudFormation stack ARN
def get_stack_arn(stack_name):
    try:
        response = boto3.client('cloudformation').describe_stacks(StackName=stack_name)
        return response['Stacks'][0]['StackId']
    except boto3.exceptions.Boto3Error as e:
        logger.error(f"Error getting stack ARN: {str(e)}")
        raise

# Helper function to check status with retries
def wait_for_status(check_function, success_status, failure_status, description):
    for attempt in range(RETRIES):
        response = check_function()
        status = response.get('status')
        if status == success_status:
            return response
        if status == failure_status:
            raise Exception(f"{description} failed")
        if status in ['Pending', 'InProgress'] and attempt < RETRIES - 1:
            time.sleep(DELAY)
    raise Exception(f"{description} timed out")

# Lambda handler
def handler(event, context):
    logger.info(f"Event: {json.dumps(event)}")
    try:
        if event.get('RequestType') == 'Delete':
            return {'Status': 'SUCCESS', 'Reason': 'Delete event - no action required'}

        app_arn = event['ResourceProperties']['AppArn']
        stack_name = event['ResourceProperties']['SourceStackName']

        resilience_hub = boto3.client('resiliencehub')
        stack_arn = get_stack_arn(stack_name)

        resilience_hub.import_resources_to_draft_app_version(appArn=app_arn, sourceArns=[stack_arn])
        wait_for_status(lambda: resilience_hub.describe_draft_app_version_resources_import_status(appArn=app_arn),
                        'Success', 'Failed', 'Import resources')

        # Debugging-only operations
        """
        logger.debug("Starting debugging-only operations")
        try:
            resilience_hub.resolve_app_version_resources(appArn=app_arn, appVersion='draft')
            wait_for_status(lambda: resilience_hub.describe_app_version_resources_resolution_status(appArn=app_arn, appVersion='draft'),
                            'Success', 'Failed', 'Resolve resources')

            resources = resilience_hub.list_app_version_resources(appArn=app_arn, appVersion='draft').get('physicalResources', [])
            if not resources:
                logger.warning("No resources found after import")
            else:
                logger.info(f"Found {len(resources)} resources in the app")
                for resource in resources:
                    logger.debug(f"Resource: {json.dumps(resource)}")   
        except Exception as debug_e:
            logger.debug(f"Debugging operation failed: {str(debug_e)}")

        return {'Status': 'SUCCESS'}
        """
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return {'Status': 'FAILED', 'Reason': str(e)}
