import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import { TableClass } from 'aws-cdk-lib/aws-dynamodb';
import { ECSConstruct } from './constructs/ecs-construct';
import * as events from "aws-cdk-lib/aws-events";
import {DockerImageCode, DockerImageFunction} from "aws-cdk-lib/aws-lambda";
import {Platform} from "aws-cdk-lib/aws-ecr-assets";
import {Duration} from "aws-cdk-lib";
import {Effect, Role, ServicePrincipal, PolicyStatement} from "aws-cdk-lib/aws-iam";
import {RetentionDays} from "aws-cdk-lib/aws-logs";

const path = require('path');

const SCHEDULE_STOCK_ANALYST = {
    weekDay: 'MON#1', //
    hour: '3',
    minute: '30',
    month: '*'
}

const SCHEDULE_PORTFOLIO_MANAGER= {
    weekDay: 'MON#1', // MO-FRI
    hour: '13',
    minute: '30', // Start at market opening in US
    month: '*'
}

export class InfrastructureStack extends cdk.Stack {
    constructor(scope: Construct, id: string, props?: cdk.StackProps) {
        super(scope, id, props);

        const stockAnalystRule = new events.Rule(this, "DailyStockAnalystRule", {
            ruleName: 'stockAnalystRule',
             // UTC time
            schedule: events.Schedule.cron(SCHEDULE_STOCK_ANALYST), // MON-FRI
        });

        const portfolioManagerRule = new events.Rule(this, "DailyPortfolioManagerRule", {
            ruleName: 'portfolioManagerRule',
             // UTC time
            schedule: events.Schedule.cron(SCHEDULE_PORTFOLIO_MANAGER), // MON-FRI
        });

        // Create DynamoDB Tables
        const createDynamoDBTable = (tableName: string, partitionKey: string, sortKey: string) => new dynamodb.TableV2(this, tableName, {
            tableName: tableName,
            partitionKey: { name: partitionKey, type: dynamodb.AttributeType.STRING},
            sortKey: { name: sortKey, type: dynamodb.AttributeType.STRING},
            billing: dynamodb.Billing.onDemand(),
            tableClass: TableClass.STANDARD,
            deletionProtection: true,
        });

        const stockAnalyticsTable = createDynamoDBTable('StockAnalytics', 'stock', 'date');
        const portfolioTable = createDynamoDBTable('Portfolio', 'stock', 'date');
        const realizedGainsTable = createDynamoDBTable('RealizedGains', 'key', 'date');

        const ecsInfrastructure = new ECSConstruct(this, 'ECSInfrastructure', {
            stockAnalyticsTable: stockAnalyticsTable.tableName,
            portfolioTable: portfolioTable.tableName,
            realizedGainsTable: realizedGainsTable.tableName,
            region: this.region,
        });

        // Add targets to EventBridge-rule
        stockAnalystRule.addTarget(ecsInfrastructure.stockAnalyst);
        portfolioManagerRule.addTarget(ecsInfrastructure.portfolioManager);

        // Grant full access to container
        portfolioTable.grantFullAccess(ecsInfrastructure.taskDefinitionStockAnalyst.taskRole);
        realizedGainsTable.grantFullAccess(ecsInfrastructure.taskDefinitionStockAnalyst.taskRole);
        stockAnalyticsTable.grantFullAccess(ecsInfrastructure.taskDefinitionStockAnalyst.taskRole);
        portfolioTable.grantFullAccess(ecsInfrastructure.taskDefinitionPortfolioManager.taskRole);
        realizedGainsTable.grantFullAccess(ecsInfrastructure.taskDefinitionPortfolioManager.taskRole);
        stockAnalyticsTable.grantFullAccess(ecsInfrastructure.taskDefinitionPortfolioManager.taskRole);

        // Bedrock Agent AWS Lambda
        const dockerfileDir = path.join(__dirname, '../../src/lambda/');
        const functionName = 'BedrockAgentInternetSearch'
        const bedrockInternetSearch = new DockerImageFunction(this, 'BedrockAgentInternetSearch', {
            code: DockerImageCode.fromImageAsset(dockerfileDir, {
                platform: Platform.LINUX_AMD64,
                cmd: ["internet_search.lambda_handler"],
            }),
            functionName: functionName,
            memorySize: 4048,
            logRetention: RetentionDays.ONE_MONTH,
            timeout: Duration.minutes(10)
        });//

        bedrockInternetSearch.addPermission('PermitBedrockInvoke', {
          principal: new ServicePrincipal('bedrock.amazonaws.com'),
        });

        bedrockInternetSearch.addToRolePolicy(new PolicyStatement({
          effect: Effect.ALLOW,
          actions: ["lambda:UpdateFunctionConfiguration"],
          resources: [`arn:aws:lambda:${this.region}:${this.account}:function:${functionName}`],
         }))

        //IAM Role for agent
        const agentRole = new Role(this, 'BedrockAgentRole', {
          assumedBy: new ServicePrincipal('bedrock.amazonaws.com'),
        });

        agentRole.addToPolicy(
          new PolicyStatement({
            effect: Effect.ALLOW,
            resources: [`arn:aws:bedrock:${this.region}::foundation-model/anthropic.claude-v2:1`],
            actions: [
              'bedrock:InvokeModel'
            ]
          })
        );
    }
}
