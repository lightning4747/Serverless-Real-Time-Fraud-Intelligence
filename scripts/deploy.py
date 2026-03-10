#!/usr/bin/env python3
"""Deployment script for Sentinel-AML infrastructure and Lambda functions."""

import os
import subprocess
import sys
import json
from pathlib import Path
from typing import Dict, Any


def run_command(command: str, cwd: str = None) -> tuple[bool, str]:
    """Run a shell command and return success status and output."""
    try:
        print(f"Running: {command}")
        result = subprocess.run(
            command.split(),
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True
        )
        print(f"✓ Success: {command}")
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed: {command}")
        print(f"Error: {e.stderr}")
        return False, e.stderr


def check_aws_credentials():
    """Check if AWS credentials are configured."""
    print("Checking AWS credentials...")
    
    success, output = run_command("aws sts get-caller-identity")
    if success:
        identity = json.loads(output)
        print(f"✓ AWS credentials configured for account: {identity['Account']}")
        return True, identity
    else:
        print("✗ AWS credentials not configured")
        return False, None


def bootstrap_cdk(account_id: str, region: str):
    """Bootstrap CDK for the account and region."""
    print(f"\nBootstrapping CDK for account {account_id} in region {region}...")
    
    success, _ = run_command(f"cdk bootstrap aws://{account_id}/{region}", cwd="infrastructure")
    if success:
        print("✓ CDK bootstrap completed")
        return True
    else:
        print("✗ CDK bootstrap failed")
        return False


def deploy_infrastructure():
    """Deploy AWS infrastructure using CDK."""
    print("\nDeploying AWS infrastructure...")
    
    # First, synthesize to check for errors
    success, _ = run_command("cdk synth", cwd="infrastructure")
    if not success:
        print("✗ CDK synthesis failed")
        return False
    
    # Deploy all stacks
    success, _ = run_command("cdk deploy --all --require-approval never", cwd="infrastructure")
    if success:
        print("✓ Infrastructure deployment completed")
        return True
    else:
        print("✗ Infrastructure deployment failed")
        return False


def get_stack_outputs():
    """Get CDK stack outputs."""
    print("\nRetrieving stack outputs...")
    
    success, output = run_command("aws cloudformation describe-stacks", cwd="infrastructure")
    if not success:
        print("⚠ Could not retrieve stack outputs")
        return {}
    
    try:
        stacks_data = json.loads(output)
        outputs = {}
        
        for stack in stacks_data['Stacks']:
            if 'SentinelAML' in stack['StackName']:
                stack_outputs = stack.get('Outputs', [])
                for output_item in stack_outputs:
                    outputs[output_item['OutputKey']] = output_item['OutputValue']
        
        print("✓ Retrieved stack outputs")
        return outputs
    except (json.JSONDecodeError, KeyError) as e:
        print(f"⚠ Error parsing stack outputs: {e}")
        return {}


def update_lambda_functions():
    """Update Lambda function code."""
    print("\nUpdating Lambda function code...")
    
    # Package Lambda functions
    lambda_functions = [
        "sentinel-aml-transaction-processor",
        "sentinel-aml-fraud-scorer", 
        "sentinel-aml-sar-generator",
        "sentinel-aml-alert-manager",
        "sentinel-aml-report-retriever",
        "sentinel-aml-health-checker",
        "sentinel-aml-orchestrator-trigger"
    ]
    
    # Create deployment package
    print("Creating deployment package...")
    
    # Create temporary directory for packaging
    package_dir = Path("dist")
    package_dir.mkdir(exist_ok=True)
    
    # Copy source code
    success, _ = run_command(f"cp -r src/* {package_dir}/")
    if not success:
        print("✗ Failed to copy source code")
        return False
    
    # Install dependencies to package directory
    success, _ = run_command(f"pip install -r requirements.txt -t {package_dir}/")
    if not success:
        print("✗ Failed to install dependencies")
        return False
    
    # Create zip file
    success, _ = run_command(f"zip -r lambda-package.zip .", cwd=str(package_dir))
    if not success:
        print("✗ Failed to create deployment package")
        return False
    
    # Update each Lambda function
    for function_name in lambda_functions:
        print(f"Updating {function_name}...")
        success, _ = run_command(
            f"aws lambda update-function-code --function-name {function_name} --zip-file fileb://{package_dir}/lambda-package.zip"
        )
        if success:
            print(f"✓ Updated {function_name}")
        else:
            print(f"⚠ Failed to update {function_name}")
    
    # Cleanup
    run_command(f"rm -rf {package_dir}")
    
    return True


def run_smoke_tests(outputs: Dict[str, Any]):
    """Run basic smoke tests against deployed infrastructure."""
    print("\nRunning smoke tests...")
    
    # Test API Gateway health endpoint
    if 'APIGatewayURL' in outputs:
        api_url = outputs['APIGatewayURL']
        health_url = f"{api_url}health"
        
        success, _ = run_command(f"curl -f {health_url}")
        if success:
            print("✓ API Gateway health check passed")
        else:
            print("⚠ API Gateway health check failed")
    
    # Test Neptune connectivity (if endpoint available)
    if 'NeptuneEndpoint' in outputs:
        print("✓ Neptune endpoint available")
        # Additional Neptune connectivity tests could be added here
    
    return True


def main():
    """Main deployment function."""
    print("🚀 Deploying Sentinel-AML infrastructure...\n")
    
    # Check AWS credentials
    success, identity = check_aws_credentials()
    if not success:
        print("\n❌ Please configure AWS credentials first:")
        print("  aws configure")
        sys.exit(1)
    
    account_id = identity['Account']
    region = os.getenv('AWS_REGION', 'us-east-1')
    
    # Deployment steps
    steps = [
        ("CDK Bootstrap", lambda: bootstrap_cdk(account_id, region)),
        ("Infrastructure Deployment", deploy_infrastructure),
        ("Lambda Function Updates", update_lambda_functions),
    ]
    
    failed_steps = []
    for step_name, step_func in steps:
        print(f"\n{'='*20} {step_name} {'='*20}")
        if not step_func():
            failed_steps.append(step_name)
            
            # Ask user if they want to continue
            response = input(f"\n{step_name} failed. Continue with remaining steps? (y/N): ")
            if response.lower() != 'y':
                break
    
    # Get stack outputs
    outputs = get_stack_outputs()
    
    # Run smoke tests
    if not failed_steps:
        run_smoke_tests(outputs)
    
    # Summary
    print("\n" + "="*60)
    if failed_steps:
        print("❌ Deployment completed with errors:")
        for step in failed_steps:
            print(f"  - {step}")
        print("\nPlease resolve the errors and run deployment again.")
        sys.exit(1)
    else:
        print("✅ Deployment completed successfully!")
        
        if outputs:
            print("\n📋 Important endpoints:")
            for key, value in outputs.items():
                print(f"  {key}: {value}")
        
        print("\n🔧 Next steps:")
        print("1. Test API endpoints")
        print("2. Configure monitoring alerts")
        print("3. Set up data ingestion")
        print("4. Run integration tests")


if __name__ == "__main__":
    main()