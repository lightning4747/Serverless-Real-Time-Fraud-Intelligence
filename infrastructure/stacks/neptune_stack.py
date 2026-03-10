"""Neptune stack for Sentinel-AML graph database."""

from aws_cdk import (
    Stack,
    aws_neptune as neptune,
    aws_ec2 as ec2,
    aws_kms as kms,
    RemovalPolicy,
)
from constructs import Construct


class NeptuneStack(Stack):
    """Neptune graph database stack for Sentinel-AML."""
    
    def __init__(self, scope: Construct, construct_id: str, kms_key: kms.Key, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # VPC for Neptune cluster
        self.vpc = ec2.Vpc(
            self, "SentinelAMLVPC",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                )
            ]
        )
        
        # Security group for Neptune
        self.neptune_security_group = ec2.SecurityGroup(
            self, "NeptuneSecurityGroup",
            vpc=self.vpc,
            description="Security group for Neptune cluster",
            allow_all_outbound=True
        )
        
        # Allow inbound connections on Neptune port
        self.neptune_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(8182),
            description="Neptune Gremlin port"
        )
        
        # Lambda security group (for Neptune access)
        self.lambda_security_group = ec2.SecurityGroup(
            self, "LambdaSecurityGroup",
            vpc=self.vpc,
            description="Security group for Lambda functions",
            allow_all_outbound=True
        )
        
        # Allow Lambda to connect to Neptune
        self.neptune_security_group.add_ingress_rule(
            peer=self.lambda_security_group,
            connection=ec2.Port.tcp(8182),
            description="Lambda to Neptune access"
        )
        
        # Neptune subnet group
        self.neptune_subnet_group = neptune.CfnDBSubnetGroup(
            self, "NeptuneSubnetGroup",
            db_subnet_group_description="Subnet group for Neptune cluster",
            subnet_ids=[subnet.subnet_id for subnet in self.vpc.private_subnets],
            db_subnet_group_name="sentinel-aml-neptune-subnet-group"
        )
        
        # Neptune parameter group
        self.neptune_parameter_group = neptune.CfnDBParameterGroup(
            self, "NeptuneParameterGroup",
            family="neptune1.2",
            description="Parameter group for Sentinel-AML Neptune cluster",
            name="sentinel-aml-neptune-params",
            parameters={
                "neptune_enable_audit_log": "1",
                "neptune_ml_iam_role": "",  # Will be set after ML role creation
                "neptune_query_timeout": "120000"  # 2 minutes
            }
        )
        
        # Neptune cluster parameter group
        self.neptune_cluster_parameter_group = neptune.CfnDBClusterParameterGroup(
            self, "NeptuneClusterParameterGroup",
            family="neptune1.2",
            description="Cluster parameter group for Sentinel-AML Neptune",
            name="sentinel-aml-neptune-cluster-params",
            parameters={
                "neptune_enable_audit_log": "1"
            }
        )
        
        # Neptune cluster
        self.neptune_cluster = neptune.CfnDBCluster(
            self, "NeptuneCluster",
            db_cluster_identifier="sentinel-aml-neptune-cluster",
            engine="neptune",
            engine_version="1.2.1.0",
            
            # Security and networking
            vpc_security_group_ids=[self.neptune_security_group.security_group_id],
            db_subnet_group_name=self.neptune_subnet_group.db_subnet_group_name,
            
            # Parameter groups
            db_cluster_parameter_group_name=self.neptune_cluster_parameter_group.ref,
            
            # Backup and maintenance
            backup_retention_period=7,
            preferred_backup_window="03:00-04:00",
            preferred_maintenance_window="sun:04:00-sun:05:00",
            
            # Encryption
            storage_encrypted=True,
            kms_key_id=kms_key.key_arn,
            
            # Deletion protection (disable for development)
            deletion_protection=False,
            
            # Enable IAM database authentication
            iam_auth_enabled=True,
            
            # Enable logging
            enable_cloudwatch_logs_exports=["audit"],
            
            # Tags
            tags=[
                {
                    "key": "Name",
                    "value": "Sentinel-AML Neptune Cluster"
                },
                {
                    "key": "Purpose", 
                    "value": "AML Graph Database"
                }
            ]
        )
        
        # Add dependency
        self.neptune_cluster.add_dependency(self.neptune_subnet_group)
        self.neptune_cluster.add_dependency(self.neptune_cluster_parameter_group)
        
        # Neptune instance (primary)
        self.neptune_instance = neptune.CfnDBInstance(
            self, "NeptunePrimaryInstance",
            db_instance_class="db.t3.medium",  # Cost-effective for development
            db_cluster_identifier=self.neptune_cluster.ref,
            engine="neptune",
            
            # Parameter group
            db_parameter_group_name=self.neptune_parameter_group.ref,
            
            # Availability zone (optional - let AWS choose)
            # availability_zone="us-east-1a",
            
            tags=[
                {
                    "key": "Name",
                    "value": "Sentinel-AML Neptune Primary"
                }
            ]
        )
        
        # Add dependency
        self.neptune_instance.add_dependency(self.neptune_cluster)
        self.neptune_instance.add_dependency(self.neptune_parameter_group)
        
        # Store important attributes
        self.cluster_endpoint = self.neptune_cluster.attr_endpoint
        self.cluster_port = self.neptune_cluster.attr_port
        self.cluster_resource_id = self.neptune_cluster.attr_cluster_resource_id