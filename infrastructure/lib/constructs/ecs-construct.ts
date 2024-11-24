import {Construct} from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import {RetentionDays} from "aws-cdk-lib/aws-logs";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as iam from 'aws-cdk-lib/aws-iam'
import * as path from 'path';

export interface ECSProps {
    stockAnalyticsTable: string;
    portfolioTable: string;
    realizedGainsTable: string;
    region: string;
}

export class ECSConstruct extends Construct {
    public readonly vpc: ec2.Vpc;
    public readonly cluster: ecs.Cluster;
    public readonly taskDefinitionStockAnalyst: ecs.FargateTaskDefinition;
    public readonly stockAnalyst: targets.EcsTask;

    public readonly taskDefinitionPortfolioManager: ecs.FargateTaskDefinition;

    public readonly portfolioManager: targets.EcsTask;

    constructor(scope: Construct, id: string, props: ECSProps) {
        super(scope, id);

        // VPC
        this.vpc = new ec2.Vpc(this, 'ECSVPC', {
            ipAddresses: ec2.IpAddresses.cidr('10.0.0.0/24'),
            maxAzs: 2,
            enableDnsSupport: true,
            enableDnsHostnames: true,
            createInternetGateway: true,
            natGateways: 0,
            vpcName: 'ECSVPC',
            restrictDefaultSecurityGroup: false,
            // Only public subnets to reduce costs
            subnetConfiguration: [
                {
                    cidrMask: 26,
                    name: 'ECSVPC/Public',
                    subnetType: ec2.SubnetType.PUBLIC,
                }]
        });

        const container = ecs.ContainerImage.fromAsset(path.join(__dirname, '../../../src/'), {
            assetName: 'Container'
        });

        // ECS Cluster
        this.cluster = new ecs.Cluster(this, 'Cluster', {
            clusterName: 'Cluster',
            vpc: this.vpc,
        });

        const containerTaskRole = new iam.Role(this, 'ECSTaskRole', {
            assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com')
        })

        containerTaskRole.addManagedPolicy(iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonBedrockFullAccess'))

        // Stock Analyst
        this.taskDefinitionStockAnalyst = new ecs.FargateTaskDefinition(this, 'TaskDefStockAnalyst', {
            runtimePlatform: {
                operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
                cpuArchitecture: ecs.CpuArchitecture.ARM64,
            },
            taskRole: containerTaskRole,
            cpu: 2048,
            memoryLimitMiB: 8192,
        });

        const stockAnalytics = this.taskDefinitionStockAnalyst.addContainer('StockAnalystContainer', {
            containerName: 'StockAnalystContainer',
            image: container,
            memoryLimitMiB: 8192,
            cpu: 2048,
            logging: ecs.LogDriver.awsLogs({
                streamPrefix: 'stockAnalyst',
                logRetention: RetentionDays.ONE_MONTH
            }),
        });

        stockAnalytics.addEnvironment('TABLE_NAME_STOCK_ANALYTICS', props.stockAnalyticsTable);
        stockAnalytics.addEnvironment('TABLE_NAME_PORTFOLIO', props.portfolioTable);
        stockAnalytics.addEnvironment('TABLE_NAME_REALIZED_GAINS', props.realizedGainsTable);
        stockAnalytics.addEnvironment('REGION', props.region);
        stockAnalytics.addEnvironment('ROLE', 'STOCK_ANALYST');

        this.stockAnalyst = new targets.EcsTask({
            cluster: this.cluster,
            taskDefinition: this.taskDefinitionStockAnalyst,
            taskCount: 1,
            subnetSelection: { subnetType: ec2.SubnetType.PUBLIC },
            assignPublicIp: true,
        });

        // Portfolio Manager
        this.taskDefinitionPortfolioManager = new ecs.FargateTaskDefinition(this, 'TaskDefPortfolioManager', {
            runtimePlatform: {
                operatingSystemFamily: ecs.OperatingSystemFamily.LINUX,
                cpuArchitecture: ecs.CpuArchitecture.ARM64,
            },
            taskRole: containerTaskRole,
            cpu: 2048,
            memoryLimitMiB: 8192,
        });

        const portfolioManager = this.taskDefinitionPortfolioManager.addContainer('PortfolioManagerContainer', {
            containerName: 'PortfolioManagerContainer',
            image: container,
            memoryLimitMiB: 8192,
            cpu: 2048,
            logging: ecs.LogDriver.awsLogs({
                streamPrefix: 'portfolioManager',
                logRetention: RetentionDays.ONE_MONTH
            }),
        });

        portfolioManager.addEnvironment('TABLE_NAME_STOCK_ANALYTICS', props.stockAnalyticsTable);
        portfolioManager.addEnvironment('TABLE_NAME_PORTFOLIO', props.portfolioTable);
        portfolioManager.addEnvironment('TABLE_NAME_REALIZED_GAINS', props.realizedGainsTable);
        portfolioManager.addEnvironment('REGION', props.region);
        portfolioManager.addEnvironment('ROLE', 'PORTFOLIO_MANAGER');

        this.portfolioManager = new targets.EcsTask({
            cluster: this.cluster,
            taskDefinition: this.taskDefinitionPortfolioManager,
            taskCount: 1,
            subnetSelection: { subnetType: ec2.SubnetType.PUBLIC },
            assignPublicIp: true,
        });
    }
}