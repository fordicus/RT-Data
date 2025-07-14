# Docker Desktop + VS Code Integration for Cross-Platform Development

## Quick Tips

💡 **Useful Commands and Shortcuts:**
- `docker info`: Check Docker's current configuration and status.
- `Open VS Code's integrated terminal (Ctrl+`)`: Quickly access Docker CLI commands within VS Code.

These commands and shortcuts are essential for verifying your setup and streamlining your development workflow.

---

## Overview

This guide provides a comprehensive setup for cross-platform development workflows where:
- **Development** is performed on Windows
- **Deployment** targets Ubuntu/Linux environments
- **Testing** occurs in containerized environments identical to production

By combining Docker Desktop with VS Code Docker Extension, developers can seamlessly build, test, and deploy applications without leaving their Windows development environment while ensuring complete compatibility with Linux deployment targets.

**Key Benefits:**
- Eliminate "it works on my machine" issues
- Test in production-like environments during development
- Leverage VS Code's integrated terminal for Docker-based testing
- Maintain consistent development experience across team members

---

## Prerequisites

Before proceeding, ensure you have:
- Windows 10/11 (Home or Pro edition)
- Administrator privileges for system configuration
- Stable internet connection for downloading components
- At least 4GB of available RAM (8GB recommended)
- 20GB of free disk space

---

## Part 1: Installing Docker Desktop with WSL2 Backend

### System Requirements Check

First, verify your system meets the requirements:

```powershell
# Check Windows version
winver

# Check if virtualization is enabled
systeminfo | findstr /C:"Hyper-V"
```

### Step 1: Install WSL2 Foundation

If WSL is not already installed, enable it manually:

1. **Enable WSL and Virtual Machine Platform**:
   - Open PowerShell as Administrator
   - Run the following commands:
     ```powershell
     dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
     dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
     ```
   - Restart your computer to apply changes

2. **Install WSL2 and set as default**:
   ```powershell
   wsl --install
   wsl --set-default-version 2
   ```

3. **Install Ubuntu distribution**:
   ```powershell
   wsl --install -d Ubuntu
   ```
   - On first launch, create a username and password
   - This will be your primary Linux environment

### Step 2: Install Docker Desktop

1. **Download Docker Desktop**:
   - Visit [Docker Desktop official page](https://www.docker.com/products/docker-desktop)
   - Download the installer for Windows

2. **Install with WSL2 backend**:
   - Run the installer as Administrator
   - **Important**: Select "Use WSL 2 instead of Hyper-V" (required for Windows Home)
   - Optionally uncheck "Start Docker Desktop when you log in" for manual control
   - Complete installation and restart if prompted

3. **Initial Docker Desktop configuration**:
   - Launch Docker Desktop
   - Accept the license agreement
   - Wait for Docker Desktop to start (this may take a few minutes)

### Step 3: Configure WSL Integration

1. **Open Docker Desktop Settings**:
   - Click the gear icon (⚙️) in the top-right corner
   - Navigate to **Settings**

2. **Verify WSL2 Engine**:
   - Go to **General** tab
   - Ensure **"Use the WSL 2 based engine"** is checked
   - This should be automatically selected on Windows Home

3. **Enable WSL Integration**:
   - Navigate to **Resources** → **WSL Integration**
   - Check **"Enable integration with my default WSL distro"**
   - Select your Ubuntu distribution from the list
   - Click **"Apply & Restart"**

### Step 4: Verify Installation

Test the setup in your Ubuntu WSL environment:

```bash
# Open Ubuntu terminal and test Docker
docker version
docker run hello-world

# If successful, you should see "Hello from Docker!" message
```

**Optional**: Add your user to the docker group to avoid using `sudo`:
```bash
sudo usermod -aG docker $USER
```
Restart WSL to apply: `wsl --shutdown` then reopen Ubuntu terminal.

---

## Part 2: VS Code Docker Extension Setup

### Step 1: Install VS Code Docker Extension

1. **Open VS Code**
2. **Install Docker Extension**:
   - Click Extensions icon (Ctrl+Shift+X)
   - Search for "Docker"
   - Install the official "Docker" extension by Microsoft
   - The extension should automatically detect your Docker Desktop installation

### Step 2: Verify VS Code Integration

1. **Check Docker Extension Status**:
   - Look for the Docker icon in the VS Code sidebar
   - You should see your containers, images, and networks listed

2. **Test Integration**:
   - Open VS Code's integrated terminal (Ctrl+`)
   - Run: `docker version`
   - The output should match what you see in Ubuntu WSL

---

## Part 3: Verification and Troubleshooting

### Comprehensive System Check

Run these commands to verify your complete setup:

#### 1. Docker Status Verification
```bash
# Check if Docker is running in Linux container mode
docker info

# Look for:
# - Operating System: Docker Desktop
# - OSType: linux
# - Architecture: x86_64
```

#### 2. WSL Status Verification
```bash
# List all WSL distributions
wsl -l -v

# Should show Ubuntu running on WSL version 2
```

#### 3. Docker Context Verification
```bash
# Check Docker context
docker context ls

# The default context should be active
```

### Common Issues and Solutions

#### Issue 1: Docker Desktop Won't Start
- **Solution**: Ensure WSL2 is properly installed and enabled
- **Check**: Run `wsl --status` to verify WSL2 is available
- **Fix**: Restart Docker Desktop or reboot your system

#### Issue 2: VS Code Can't Connect to Docker
- **Solution**: Verify Docker Desktop is running and the extension is properly installed
- **Check**: Look for Docker icon in VS Code sidebar
- **Fix**: Restart VS Code or reinstall the Docker extension

#### Issue 3: Permission Denied in WSL
- **Solution**: Add your user to the docker group:
  ```bash
  sudo usermod -aG docker $USER
  ```
- **Apply**: Restart WSL with `wsl --shutdown`

#### Issue 4: Windows Container Mode Active
- **Check**: Run `docker info` and look for `OSType: windows`
- **Fix**: 
  - Right-click Docker Desktop system tray icon
  - Select "Switch to Linux containers"
  - Wait for Docker to restart

---

## Part 4: Development Workflow Integration

### Testing with Docker in VS Code

1. **Open your project in VS Code**
2. **Use integrated terminal** (Ctrl+`) for Docker commands
3. **Build and test** using the same commands as your Ubuntu deployment:
   ```bash
   # Example: Build your application
   docker build -t my-app .
   
   # Example: Run your application
   docker run -p 8000:8000 my-app
   ```

### Best Practices

1. **Use Docker Compose** for multi-service applications
2. **Mount your code** as volumes for rapid development
3. **Use .dockerignore** to exclude unnecessary files
4. **Test environment variables** that match your production setup

### VS Code Features to Leverage

- **Docker Extension**: Browse containers, images, and networks
- **Command Palette**: Quick access to Docker commands (Ctrl+Shift+P)
- **Integrated Terminal**: Seamless Docker CLI access
- **Remote Development**: Edit files directly in containers

---

## Conclusion

You now have a complete cross-platform development environment that allows you to:
- Develop on Windows with native performance
- Test in Linux containers identical to production
- Deploy to Ubuntu servers with confidence
- Use VS Code's powerful Docker integration for streamlined workflows

This setup eliminates platform-specific issues and ensures consistent behavior across development and production environments. The combination of Docker Desktop with WSL2 and VS Code provides a powerful, integrated development experience that scales from individual projects to enterprise applications.

---

## Author's Personal Note

This document `DOCKER-VS-CODE GUIDE.md` largely owes my personal LaTeX project in Overleaf:
`_rtdkp_/Reinforcement-Transformer-Docker-Kubernetes-PostgreSQL`.

---

### VS Code Terminal Configuration for Conda Environment

To ensure that the VS Code integrated terminal runs in the intended conda environment, you can define the settings in `.vscode/settings.json` as follows:

```jsonc
{
  "python.pythonPath": "${env:USERPROFILE}/anaconda3/envs/binance/bin/python",
  "terminal.integrated.defaultProfile.windows": "Command Prompt",
  "terminal.integrated.profiles.windows": {
    "Command Prompt": {
      "path": "cmd.exe",
      "args": ["/K", "conda activate binance"]
    }
  }
}
```

This configuration ensures that:
- The Python interpreter used matches the specified conda environment.
- The integrated terminal automatically activates the `binance` conda environment.

For more details, refer to the file: `<your-repository>\.vscode\settings.json`.