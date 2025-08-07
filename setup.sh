#!/bin/bash

# setup.sh - Kimovil Phone Processor List Setup Script
# This script uses uv for fast, reliable Python environment management
# Compatible with Linux, macOS, and Windows (via WSL/Git Bash)

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Print functions
print_header() {
    echo -e "${BLUE}================================================${NC}"
    echo -e "${CYAN}📱 Kimovil Phone Processor List Setup${NC}"
    echo -e "${BLUE}================================================${NC}"
    echo ""
}

print_step() {
    echo -e "${BLUE}🔧 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ️  $1${NC}"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Install uv if not present
install_uv() {
    if command_exists uv; then
        print_success "uv is already installed"
        uv --version
        return 0
    fi
    
    print_step "Installing uv (Universal Python Package Manager)..."
    
    # Detect OS and install accordingly
    case "$(uname -s)" in
        Linux*)
            if command_exists curl; then
                curl -LsSf https://astral.sh/uv/install.sh | sh
            elif command_exists wget; then
                wget -qO- https://astral.sh/uv/install.sh | sh
            else
                print_error "Neither curl nor wget found. Please install one of them first."
                exit 1
            fi
            ;;
        Darwin*)
            if command_exists brew; then
                brew install uv
            elif command_exists curl; then
                curl -LsSf https://astral.sh/uv/install.sh | sh
            else
                print_error "Please install Homebrew or curl first."
                exit 1
            fi
            ;;
        CYGWIN*|MINGW32*|MSYS*|MINGW*)
            if command_exists curl; then
                curl -LsSf https://astral.sh/uv/install.sh | sh
            elif command_exists powershell; then
                powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
            else
                print_error "Please install curl or use PowerShell for Windows."
                exit 1
            fi
            ;;
        *)
            print_error "Unsupported operating system: $(uname -s)"
            exit 1
            ;;
    esac
    
    # Source the shell to make uv available
    export PATH="$HOME/.local/bin:$PATH"
    
    if command_exists uv; then
        print_success "uv installed successfully"
        uv --version
    else
        print_error "Failed to install uv. Please restart your terminal and try again."
        print_info "You may need to add ~/.local/bin to your PATH manually."
        exit 1
    fi
}

# Setup Python environment
setup_python_environment() {
    print_step "Setting up Python environment with uv..."
    
    # Check if we're in a project directory
    if [ ! -f "requirements.txt" ]; then
        print_error "requirements.txt not found. Please run this script from the project directory."
        exit 1
    fi
    
    # Create or sync the virtual environment with dependencies
    print_info "Creating virtual environment and installing dependencies..."
    
    # Use uv to create a project environment and install dependencies
    if uv venv venv --python 3.12; then
        print_success "Virtual environment created successfully"
    else
        print_warning "Virtual environment creation had issues, but continuing..."
    fi
    
    # Activate the virtual environment
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
        print_success "Virtual environment activated"
    elif [ -f "venv/Scripts/activate" ]; then
        source venv/Scripts/activate
        print_success "Virtual environment activated (Windows)"
    else
        print_warning "Could not find activation script, but continuing..."
    fi
    
    # Install dependencies using uv
    print_info "Installing Python dependencies..."
    if uv pip install -r requirements.txt; then
        print_success "Python dependencies installed successfully"
    else
        print_error "Failed to install Python dependencies"
        exit 1
    fi
}

# Install Playwright browsers
install_playwright_browsers() {
    print_step "Installing Playwright browser binaries..."
    print_info "This may take a few minutes as it downloads browser binaries..."
    
    # Activate virtual environment if it exists
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    elif [ -f "venv/Scripts/activate" ]; then
        source venv/Scripts/activate
    fi
    
    # Install playwright browsers
    if python -m playwright install chromium; then
        print_success "Playwright Chromium browser installed successfully"
    else
        print_warning "Playwright browser installation had issues"
        print_info "You may need to run 'python -m playwright install' manually later"
    fi
    
    # Install system dependencies for playwright (Linux only)
    if [ "$(uname -s)" = "Linux" ]; then
        print_info "Installing system dependencies for Playwright on Linux..."
        if python -m playwright install-deps chromium 2>/dev/null; then
            print_success "System dependencies installed"
        else
            print_warning "System dependencies installation had issues"
            print_info "You may need to install them manually with: python -m playwright install-deps"
        fi
    fi
}

# Verify installation
verify_installation() {
    print_step "Verifying installation..."
    
    # Activate virtual environment if it exists
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    elif [ -f "venv/Scripts/activate" ]; then
        source venv/Scripts/activate
    fi
    
    # Test Python and key imports
    if python -c "
import sys
print(f'Python version: {sys.version}')

try:
    import playwright
    print('✅ Playwright imported successfully')
except ImportError as e:
    print(f'❌ Playwright import failed: {e}')
    sys.exit(1)

try:
    import bs4
    print('✅ BeautifulSoup4 imported successfully')
except ImportError as e:
    print(f'❌ BeautifulSoup4 import failed: {e}')
    sys.exit(1)

try:
    import rich
    print('✅ Rich imported successfully')
except ImportError as e:
    print(f'❌ Rich import failed: {e}')
    sys.exit(1)

print('🎉 All dependencies verified successfully!')
"; then
        print_success "Installation verification completed successfully"
    else
        print_error "Installation verification failed"
        exit 1
    fi
}

# Print usage instructions
print_usage_instructions() {
    echo ""
    print_success "🎉 Setup completed successfully!"
    echo ""
    echo -e "${CYAN}📋 Usage Instructions:${NC}"
    echo -e "${YELLOW}1.${NC} Activate the virtual environment:"
    if [ "$(uname -s)" = "Linux" ] || [ "$(uname -s)" = "Darwin" ]; then
        echo -e "   ${GREEN}source venv/bin/activate${NC}"
    else
        echo -e "   ${GREEN}venv\\Scripts\\activate${NC}"
    fi
    echo ""
    echo -e "${YELLOW}2.${NC} Run the phone data fetcher:"
    echo -e "   ${GREEN}python list_phones_by_processor.py${NC}"
    echo ""
    echo -e "${YELLOW}3.${NC} To run with GUI (if available):"
    echo -e "   ${GREEN}python list_phones_by_processor.py --gui${NC}"
    echo ""
    echo -e "${YELLOW}4.${NC} To deactivate the virtual environment when done:"
    echo -e "   ${GREEN}deactivate${NC}"
    echo ""
    echo -e "${CYAN}📁 Project Files:${NC}"
    echo -e "   • ${GREEN}list_phones_by_processor.py${NC} - Main script"
    echo -e "   • ${GREEN}requirements.txt${NC} - Python dependencies"
    echo -e "   • ${GREEN}venv/${NC} - Virtual environment"
    echo ""
    echo -e "${CYAN}🔧 Troubleshooting:${NC}"
    echo -e "   • If browsers fail to load: ${GREEN}python -m playwright install${NC}"
    echo -e "   • For system deps on Linux: ${GREEN}python -m playwright install-deps${NC}"
    echo ""
    echo -e "${BLUE}================================================${NC}"
}

# Main execution
main() {
    print_header
    
    # Check if running from correct directory
    if [ ! -f "list_phones_by_processor.py" ] || [ ! -f "requirements.txt" ]; then
        print_error "Please run this script from the project root directory"
        print_info "Expected files: list_phones_by_processor.py, requirements.txt"
        exit 1
    fi
    
    # Install uv
    install_uv
    
    # Setup Python environment and install dependencies
    setup_python_environment
    
    # Install Playwright browsers
    install_playwright_browsers
    
    # Verify installation
    verify_installation
    
    # Print usage instructions
    print_usage_instructions
}

# Run main function
main "$@"