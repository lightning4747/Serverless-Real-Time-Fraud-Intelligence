#!/usr/bin/env python3
"""Setup script for Sentinel-AML development environment."""

import os
import subprocess
import sys
from pathlib import Path


def run_command(command: str, cwd: str = None) -> bool:
    """Run a shell command and return success status."""
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
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed: {command}")
        print(f"Error: {e.stderr}")
        return False


def check_prerequisites():
    """Check if required tools are installed."""
    print("Checking prerequisites...")
    
    # Check Python version
    if sys.version_info < (3, 9):
        print("✗ Python 3.9 or higher is required")
        return False
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}")
    
    # Check Node.js for CDK
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ Node.js {result.stdout.strip()}")
        else:
            print("✗ Node.js is required for AWS CDK")
            return False
    except FileNotFoundError:
        print("✗ Node.js is required for AWS CDK")
        return False
    
    # Check AWS CLI
    try:
        result = subprocess.run(["aws", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ AWS CLI installed")
        else:
            print("⚠ AWS CLI not found - install for deployment")
    except FileNotFoundError:
        print("⚠ AWS CLI not found - install for deployment")
    
    return True


def setup_python_environment():
    """Set up Python virtual environment and dependencies."""
    print("\nSetting up Python environment...")
    
    # Create virtual environment if it doesn't exist
    if not Path("venv").exists():
        if not run_command("python -m venv venv"):
            return False
    
    # Determine activation script path
    if os.name == 'nt':  # Windows
        pip_path = "venv\\Scripts\\pip"
        python_path = "venv\\Scripts\\python"
    else:  # Unix/Linux/macOS
        pip_path = "venv/bin/pip"
        python_path = "venv/bin/python"
    
    # Upgrade pip
    if not run_command(f"{python_path} -m pip install --upgrade pip"):
        return False
    
    # Install core dependencies
    if not run_command(f"{pip_path} install -e ."):
        return False
    
    # Install development dependencies
    if not run_command(f"{pip_path} install -e .[dev]"):
        return False
    
    # Install CDK dependencies
    if not run_command(f"{pip_path} install -e .[cdk]"):
        return False
    
    print("✓ Python environment setup complete")
    return True


def setup_cdk_environment():
    """Set up AWS CDK environment."""
    print("\nSetting up AWS CDK environment...")
    
    # Install CDK globally
    if not run_command("npm install -g aws-cdk"):
        print("⚠ Failed to install CDK globally, trying local install...")
        if not run_command("npm install aws-cdk", cwd="infrastructure"):
            return False
    
    # Install CDK dependencies
    if not run_command("npm install", cwd="infrastructure"):
        return False
    
    print("✓ CDK environment setup complete")
    return True


def setup_pre_commit():
    """Set up pre-commit hooks."""
    print("\nSetting up pre-commit hooks...")
    
    # Determine python path
    if os.name == 'nt':  # Windows
        python_path = "venv\\Scripts\\python"
    else:  # Unix/Linux/macOS
        python_path = "venv/bin/python"
    
    # Install pre-commit hooks
    if not run_command(f"{python_path} -m pre_commit install"):
        return False
    
    print("✓ Pre-commit hooks setup complete")
    return True


def create_env_file():
    """Create .env file from template if it doesn't exist."""
    print("\nSetting up environment configuration...")
    
    if not Path(".env").exists():
        if Path(".env.example").exists():
            # Copy example file
            with open(".env.example", "r") as src, open(".env", "w") as dst:
                dst.write(src.read())
            print("✓ Created .env file from template")
            print("⚠ Please update .env file with your actual configuration values")
        else:
            print("⚠ .env.example not found, skipping .env creation")
    else:
        print("✓ .env file already exists")
    
    return True


def create_directories():
    """Create necessary directories."""
    print("\nCreating project directories...")
    
    directories = [
        "data",
        "notebooks", 
        "tests/unit",
        "tests/integration",
        "tests/property",
        "configs",
        "scripts",
        "docs",
        "logs"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✓ Created directory: {directory}")
    
    return True


def main():
    """Main setup function."""
    print("🚀 Setting up Sentinel-AML development environment...\n")
    
    # Check prerequisites
    if not check_prerequisites():
        print("\n❌ Prerequisites check failed. Please install required tools.")
        sys.exit(1)
    
    # Setup steps
    steps = [
        ("Python environment", setup_python_environment),
        ("CDK environment", setup_cdk_environment),
        ("Pre-commit hooks", setup_pre_commit),
        ("Environment configuration", create_env_file),
        ("Project directories", create_directories),
    ]
    
    failed_steps = []
    for step_name, step_func in steps:
        if not step_func():
            failed_steps.append(step_name)
    
    # Summary
    print("\n" + "="*50)
    if failed_steps:
        print("❌ Setup completed with errors:")
        for step in failed_steps:
            print(f"  - {step}")
        print("\nPlease resolve the errors and run setup again.")
        sys.exit(1)
    else:
        print("✅ Setup completed successfully!")
        print("\nNext steps:")
        print("1. Update .env file with your AWS configuration")
        print("2. Configure AWS credentials: aws configure")
        print("3. Bootstrap CDK: cd infrastructure && cdk bootstrap")
        print("4. Run tests: pytest")
        print("5. Deploy infrastructure: cd infrastructure && cdk deploy --all")


if __name__ == "__main__":
    main()