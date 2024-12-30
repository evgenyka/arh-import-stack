import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as resiliencehub from 'aws-cdk-lib/aws-resiliencehub';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as cr from 'aws-cdk-lib/custom-resources';

export interface ArhImportStackStackProps extends cdk.StackProps {
  resiliencyPolicyArn: string;
  sourceStackName: string;
}

export class ArhImportStackStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ArhImportStackStackProps) {
    super(scope, id, props);

    // Create Resilience Hub Application
    const arhApp = new resiliencehub.CfnApp(this, 'ResilienceHubApplication', {
      name: 'MyResilienceApp',
      description: 'Resilience configuration for my application',
      appAssessmentSchedule: 'Daily',
      resiliencyPolicyArn: props.resiliencyPolicyArn,
      appTemplateBody: '{"Resources":{}}',
      resourceMappings: [],
      tags: {
        Environment: 'Production'
      },
    });

    // Create Lambda function for importing resources
    const importFunction = new lambda.Function(this, 'ImportResourcesFunction', {
      runtime: lambda.Runtime.PYTHON_3_9,
      description: 'Import resources into Resilience Hub Application',
      handler: 'index.handler',
      code: lambda.Code.fromAsset('lambda'),
      timeout: cdk.Duration.minutes(10),
    });

    // Attach the AWS managed policy to the Lambda function's role
    importFunction.role?.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName('AWSResilienceHubAsssessmentExecutionPolicy')
    );

    // Add specific Resilience Hub permissions
    importFunction.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'resiliencehub:ImportResourcesToDraftAppVersion',
        'resiliencehub:ResolveAppVersionResources',
        'resiliencehub:DescribeDraftAppVersionResourcesImportStatus',
        'resiliencehub:ListAppVersionResources',
        'resiliencehub:DescribeAppVersionResourcesResolutionStatus'
      ],
      resources: ['*'],
    }));

    // Create Custom Resource for importing resources
    const importResources = new cr.AwsCustomResource(this, 'ImportResources', {
      onCreate: {
        service: 'Lambda',
        action: 'invoke',
        parameters: {
          FunctionName: importFunction.functionName,
          Payload: JSON.stringify({
            RequestType: 'Create',
            ResourceProperties: {
              AppArn: arhApp.attrAppArn,
              SourceStackName: props.sourceStackName,
            },
          }),
        },
        physicalResourceId: cr.PhysicalResourceId.of('ImportResources'),
      },
      policy: cr.AwsCustomResourcePolicy.fromStatements([
        new iam.PolicyStatement({
          actions: ['lambda:InvokeFunction'],
          resources: [importFunction.functionArn],
        }),
      ]),
    });

    // Grant the custom resource permission to invoke the Lambda function
    importFunction.grantInvoke(importResources.grantPrincipal);

    // Output the ARN of the created Resilience Hub Application
    new cdk.CfnOutput(this, 'ApplicationArn', {
      value: arhApp.attrAppArn,
      description: 'ARN of the created Resilience Hub Application',
    });
  }
}