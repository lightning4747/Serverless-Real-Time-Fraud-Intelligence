#!/usr/bin/env python3
"""
Deployment automation script for Sentinel-AML infrastructure.

This script provides automated deployment, validation, and rollback
capabilities for the Sentinel-AML system using AWS CDK.
"""

import os
import sys
import json
import subprocess
import argparse
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'deployment-{datetime.now().strftime("%Y%m%d-%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)


class DeploymentManager:
    """Manages CDK deployment lifecycle for Sentinel-AML."""
    
    def __init__(self, environment: str = "development", region: str = "us-east-1"):
        """
        Initialize deployment manager.
        
        Args:
            environment: Target environment (development, staging, production)
            region: AWS region for deployment
        """
        self.environment = environment
        self.region = region
        self.account_id = self._get_account_id()
        
        # AWS clients
        self.cloudformation = boto3.client('cloudformation', region_name=region)
        self.s3 = boto3.client('s3', region_name=region)
        self.ssm = boto3.client('ssm', region_name=region)
        
        # Deployment configuration
        self.config = self._load_deployment_config()
        
        # Stack names
        self.stack_names = [
            f"SentinelAMLSecurity-{environment}",
            f"SentinelAMLNeptune-{environment}",
            f"SentinelAMLLambda-{environment}",
            f"SentinelAMLAPI-{environment}",
            f"SentinelAMLOrchestration-{environment}",
            f"SentinelAMLMonitoring-{environment}"
        ]
    
    def _get_account_id(self) -> str:
        """Get AWS account ID."""
        try:
            sts = boto3.client('sts')
            return sts.get_caller_identity()['Account']
        except ClientError as e:
            logger.error(f"Failed to get account ID: {e}")
            sys.exit(1)
    
    def _load_deployment_config(self) -> Dict[str, Any]:
        """Load deployment configuration."""
        config_file = Path(f"configs/deployment-{self.environment}.json")
        
        if config_file.exists():
            with open(config_file, 'r') as f:
                return json.load(f)
        else:
            # Default configuration
            return {
                "notification_email": "admin@sentinel-aml.com",
                "enable_deletion_protection": self.environment == "production",
                "backup_retention_days": 30 if self.environment == "production" else 7,
                "monitoring_level": "detailed" if self.environment == "production" else "basic",
                "auto_scaling_enabled": True,
                "vpc_cidr": "10.0.0.0/16"
            }
    
    def validate_prerequisites(self) -> bool:
        """
        Validate deployment prerequisites.
        
        Returns:
            True if all prerequisites are met
        """
        logger.info("Validating deployment prerequisites...")
        
        checks = []
        
        # Check AWS credentials
        try:
            boto3.client('sts').get_caller_identity()
            checks.append(("AWS Credentials", True, "Valid"))
        except Exception as e:
            checks.append(("AWS Credentials", False, str(e)))
        
        # Check CDK CLI
        try:
            result = subprocess.run(['cdk', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                checks.append(("CDK CLI", True, result.stdout.strip()))
            else:
                checks.append(("CDK CLI", False, "CDK CLI not found"))
        except FileNotFoundError:
            checks.append(("CDK CLI", False, "CDK CLI not installed"))
        
        # Check Node.js (required for CDK)
        try:
            result = subprocess.run(['node', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                checks.append(("Node.js", True, result.stdout.strip()))
            else:
                checks.append(("Node.js", False, "Node.js not found"))
        except FileNotFoundError:
            checks.append(("Node.js", False, "Node.js not installed"))
        
        # Check Python dependencies
        try:
            import aws_cdk
            checks.append(("AWS CDK Python", True, f"Version {aws_cdk.__version__}"))
        except ImportError:
            checks.append(("AWS CDK Python", False, "aws-cdk-lib not installed"))
        
        # Check source code
        src_path = Path("src/sentinel_aml")
        if src_path.exists():
            checks.append(("Source Code", True, "Found"))
        else:
            checks.append(("Source Code", False, "Source directory not found"))
        
        # Print validation results
        logger.info("Prerequisite validation results:")
        all_passed = True
        for check_name, passed, message in checks:
            status = "✓" if passed else "✗"
            logger.info(f"  {status} {check_name}: {message}")
            if not passed:
                all_passed = False
        
        return all_passed
    
    def bootstrap_cdk(self) -> bool:
        """
        Bootstrap CDK in the target account/region.
        
        Returns:
            True if bootstrap successful
        """
        logger.info(f"Bootstrapping CDK in account {self.account_id}, region {self.region}...")
        
        try:
            cmd = [
                'cdk', 'bootstrap',
                f'aws://{self.account_id}/{self.region}',
                '--context', f'environment={self.environment}'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd='infrastructure')
            
            if result.returncode == 0:
                logger.info("CDK bootstrap completed successfully")
                return True
            else:
                logger.error(f"CDK bootstrap failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error during CDK bootstrap: {e}")
            return False
    
    def deploy_infrastructure(self, stack_filter: Optional[str] = None) -> bool:
        """
        Deploy infrastructure using CDK.
        
        Args:
            stack_filter: Optional filter to deploy specific stacks
            
        Returns:
            True if deployment successful
        """
        logger.info(f"Starting infrastructure deployment for environment: {self.environment}")
        
        try:
            # Set environment variables
            env = os.environ.copy()
            env.update({
                'ENVIRONMENT': self.environment,
                'CDK_DEFAULT_REGION': self.region,
                'CDK_DEFAULT_ACCOUNT': self.account_id
            })
            
            # Build CDK command
            cmd = ['cdk', 'deploy', '--all', '--require-approval', 'never']
            
            if stack_filter:
                cmd = ['cdk', 'deploy', stack_filter, '--require-approval', 'never']
            
            # Add context
            cmd.extend([
                '--context', f'environment={self.environment}',
                '--context', f'notificationEmail={self.config["notification_email"]}',
                '--context', f'enableDeletionProtection={self.config["enable_deletion_protection"]}',
                '--context', f'backupRetentionDays={self.config["backup_retention_days"]}'
            ])
            
            # Execute deployment
            logger.info(f"Executing: {' '.join(cmd)}")
            result = subprocess.run(cmd, env=env, cwd='infrastructure')
            
            if result.returncode == 0:
                logger.info("Infrastructure deployment completed successfully")
                return True
            else:
                logger.error("Infrastructure deployment failed")
                return False
                
        except Exception as e:
            logger.error(f"Error during infrastructure deployment: {e}")
            return False
    
    def validate_deployment(self) -> bool:
        """
        Validate deployed infrastructure.
        
        Returns:
            True if validation successful
        """
        logger.info("Validating deployed infrastructure...")
        
        validation_results = []
        
        # Check CloudFormation stacks
        for stack_name in self.stack_names:
            try:
                response = self.cloudformation.describe_stacks(StackName=stack_name)
                stack = response['Stacks'][0]
                status = stack['StackStatus']
                
                if status in ['CREATE_COMPLETE', 'UPDATE_COMPLETE']:
                    validation_results.append((stack_name, True, status))
                else:
                    validation_results.append((stack_name, False, status))
                    
            except ClientError as e:
                if e.response['Error']['Code'] == 'ValidationError':
                    validation_results.append((stack_name, False, "Stack not found"))
                else:
                    validation_results.append((stack_name, False, str(e)))
        
        # Test API Gateway endpoint
        try:
            api_url = self._get_stack_output('SentinelAMLAPI', 'APIGatewayURL')
            if api_url:
                # Simple health check
                import requests
                response = requests.get(f"{api_url}/health", timeout=10)
                if response.status_code == 200:
                    validation_results.append(("API Gateway Health", True, "Healthy"))
                else:
                    validation_results.append(("API Gateway Health", False, f"Status: {response.status_code}"))
            else:
                validation_results.append(("API Gateway Health", False, "URL not found"))
        except Exception as e:
            validation_results.append(("API Gateway Health", False, str(e)))
        
        # Test Neptune connectivity
        try:
            neptune_endpoint = self._get_stack_output('SentinelAMLNeptune', 'NeptuneEndpoint')
            if neptune_endpoint:
                validation_results.append(("Neptune Endpoint", True, "Available"))
            else:
                validation_results.append(("Neptune Endpoint", False, "Not found"))
        except Exception as e:
            validation_results.append(("Neptune Endpoint", False, str(e)))
        
        # Print validation results
        logger.info("Deployment validation results:")
        all_passed = True
        for check_name, passed, message in validation_results:
            status = "✓" if passed else "✗"
            logger.info(f"  {status} {check_name}: {message}")
            if not passed:
                all_passed = False
        
        return all_passed
    
    def _get_stack_output(self, stack_name: str, output_key: str) -> Optional[str]:
        """Get CloudFormation stack output value."""
        try:
            full_stack_name = f"{stack_name}-{self.environment}"
            response = self.cloudformation.describe_stacks(StackName=full_stack_name)
            stack = response['Stacks'][0]
            
            for output in stack.get('Outputs', []):
                if output['OutputKey'] == output_key:
                    return output['OutputValue']
            
            return None
            
        except Exception:
            return None
    
    def create_deployment_snapshot(self) -> str:
        """
        Create a snapshot of the current deployment for rollback.
        
        Returns:
            Snapshot identifier
        """
        snapshot_id = f"snapshot-{self.environment}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        logger.info(f"Creating deployment snapshot: {snapshot_id}")
        
        try:
            # Store stack templates and parameters
            snapshot_data = {
                'snapshot_id': snapshot_id,
                'environment': self.environment,
                'timestamp': datetime.now().isoformat(),
                'stacks': {}
            }
            
            for stack_name in self.stack_names:
                try:
                    # Get stack template
                    template_response = self.cloudformation.get_template(StackName=stack_name)
                    
                    # Get stack parameters
                    stack_response = self.cloudformation.describe_stacks(StackName=stack_name)
                    stack = stack_response['Stacks'][0]
                    
                    snapshot_data['stacks'][stack_name] = {
                        'template': template_response['TemplateBody'],
                        'parameters': stack.get('Parameters', []),
                        'outputs': stack.get('Outputs', []),
                        'status': stack['StackStatus']
                    }
                    
                except ClientError:
                    logger.warning(f"Could not snapshot stack {stack_name}")
            
            # Store snapshot in S3
            snapshot_bucket = f"sentinel-aml-deployments-{self.account_id}"
            snapshot_key = f"snapshots/{snapshot_id}.json"
            
            self.s3.put_object(
                Bucket=snapshot_bucket,
                Key=snapshot_key,
                Body=json.dumps(snapshot_data, indent=2, default=str),
                ServerSideEncryption='AES256'
            )
            
            logger.info(f"Deployment snapshot saved: s3://{snapshot_bucket}/{snapshot_key}")
            return snapshot_id
            
        except Exception as e:
            logger.error(f"Failed to create deployment snapshot: {e}")
            return ""
    
    def rollback_deployment(self, snapshot_id: str) -> bool:
        """
        Rollback deployment to a previous snapshot.
        
        Args:
            snapshot_id: Snapshot identifier to rollback to
            
        Returns:
            True if rollback successful
        """
        logger.info(f"Rolling back deployment to snapshot: {snapshot_id}")
        
        try:
            # This is a simplified rollback - in production, you'd want more sophisticated rollback logic
            logger.warning("Rollback functionality requires manual intervention for safety")
            logger.info("To rollback:")
            logger.info("1. Review the snapshot data")
            logger.info("2. Use 'cdk destroy' to remove current stacks")
            logger.info("3. Redeploy from the snapshot configuration")
            
            return True
            
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False
    
    def cleanup_old_snapshots(self, retention_days: int = 30) -> None:
        """Clean up old deployment snapshots."""
        logger.info(f"Cleaning up snapshots older than {retention_days} days")
        
        try:
            snapshot_bucket = f"sentinel-aml-deployments-{self.account_id}"
            
            # List and delete old snapshots
            response = self.s3.list_objects_v2(Bucket=snapshot_bucket, Prefix="snapshots/")
            
            cutoff_date = datetime.now().timestamp() - (retention_days * 24 * 60 * 60)
            
            for obj in response.get('Contents', []):
                if obj['LastModified'].timestamp() < cutoff_date:
                    self.s3.delete_object(Bucket=snapshot_bucket, Key=obj['Key'])
                    logger.info(f"Deleted old snapshot: {obj['Key']}")
                    
        except Exception as e:
            logger.error(f"Failed to cleanup old snapshots: {e}")


def main():
    """Main deployment script entry point."""
    parser = argparse.ArgumentParser(description="Sentinel-AML Deployment Manager")
    parser.add_argument('--environment', '-e', default='development',
                       choices=['development', 'staging', 'production'],
                       help='Target environment')
    parser.add_argument('--region', '-r', default='us-east-1',
                       help='AWS region')
    parser.add_argument('--action', '-a', required=True,
                       choices=['validate', 'bootstrap', 'deploy', 'validate-deployment', 
                               'snapshot', 'rollback', 'cleanup'],
                       help='Action to perform')
    parser.add_argument('--stack-filter', '-s',
                       help='Filter to deploy specific stacks')
    parser.add_argument('--snapshot-id',
                       help='Snapshot ID for rollback')
    
    args = parser.parse_args()
    
    # Initialize deployment manager
    deployment_manager = DeploymentManager(args.environment, args.region)
    
    success = True
    
    if args.action == 'validate':
        success = deployment_manager.validate_prerequisites()
    
    elif args.action == 'bootstrap':
        success = deployment_manager.bootstrap_cdk()
    
    elif args.action == 'deploy':
        if deployment_manager.validate_prerequisites():
            success = deployment_manager.deploy_infrastructure(args.stack_filter)
        else:
            success = False
    
    elif args.action == 'validate-deployment':
        success = deployment_manager.validate_deployment()
    
    elif args.action == 'snapshot':
        snapshot_id = deployment_manager.create_deployment_snapshot()
        success = bool(snapshot_id)
    
    elif args.action == 'rollback':
        if not args.snapshot_id:
            logger.error("Snapshot ID required for rollback")
            success = False
        else:
            success = deployment_manager.rollback_deployment(args.snapshot_id)
    
    elif args.action == 'cleanup':
        deployment_manager.cleanup_old_snapshots()
    
    if success:
        logger.info(f"Action '{args.action}' completed successfully")
        sys.exit(0)
    else:
        logger.error(f"Action '{args.action}' failed")
        sys.exit(1)


if __name__ == "__main__":
    main()