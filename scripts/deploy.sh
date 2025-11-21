#!/bin/bash

# JML Engine Deployment Script
# This script provides automated deployment options for the JML Engine

set -e

# Configuration
PROJECT_NAME="jml-engine"
DOCKER_REGISTRY="${DOCKER_REGISTRY:-localhost:5000}"
DOCKER_TAG="${DOCKER_TAG:-latest}"
ENVIRONMENT="${ENVIRONMENT:-development}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    # Check if Docker Compose is installed
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi

    # Check if .env file exists
    if [ ! -f ".env" ]; then
        log_warning ".env file not found. Creating from template..."
        if [ -f ".env.example" ]; then
            cp .env.example .env
            log_warning "Please edit .env file with your configuration before deploying."
        else
            log_error ".env.example template not found."
            exit 1
        fi
    fi

    log_success "Prerequisites check passed."
}

# Build Docker images
build_images() {
    log_info "Building Docker images..."

    # Build API image
    log_info "Building API image..."
    docker build -f Dockerfile.api -t ${DOCKER_REGISTRY}/${PROJECT_NAME}-api:${DOCKER_TAG} .

    # Build Dashboard image
    log_info "Building Dashboard image..."
    docker build -f Dockerfile.dashboard -t ${DOCKER_REGISTRY}/${PROJECT_NAME}-dashboard:${DOCKER_TAG} .

    log_success "Docker images built successfully."
}

# Deploy with Docker Compose
deploy_compose() {
    log_info "Deploying with Docker Compose..."

    # Set environment variables
    export DOCKER_REGISTRY=${DOCKER_REGISTRY}
    export DOCKER_TAG=${DOCKER_TAG}
    export ENVIRONMENT=${ENVIRONMENT}

    # Start services
    docker-compose up -d

    # Wait for services to be healthy
    log_info "Waiting for services to be healthy..."
    sleep 30

    # Check service health
    check_services_health

    log_success "Deployment completed successfully."
}

# Deploy to Kubernetes
deploy_kubernetes() {
    log_info "Deploying to Kubernetes..."

    # Check if kubectl is available
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed. Please install kubectl first."
        exit 1
    fi

    # Apply Kubernetes manifests
    kubectl apply -f k8s/

    # Wait for deployments to be ready
    kubectl wait --for=condition=available --timeout=300s deployment/jml-api
    kubectl wait --for=condition=available --timeout=300s deployment/jml-dashboard

    log_success "Kubernetes deployment completed."
}

# Check service health
check_services_health() {
    log_info "Checking service health..."

    # Check API health
    if curl -f http://localhost:8000/health &> /dev/null; then
        log_success "API service is healthy."
    else
        log_error "API service health check failed."
        exit 1
    fi

    # Check Dashboard health (if running)
    if curl -f http://localhost:8501/health &> /dev/null; then
        log_success "Dashboard service is healthy."
    else
        log_warning "Dashboard service health check failed (may not be enabled)."
    fi
}

# Run database migrations (if applicable)
run_migrations() {
    log_info "Running database migrations..."

    # This would be specific to your database setup
    # For example, if using Alembic:
    # docker-compose exec api alembic upgrade head

    log_success "Migrations completed."
}

# Backup data
backup_data() {
    log_info "Creating backup..."

    BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p ${BACKUP_DIR}

    # Backup audit logs
    if [ -d "audit" ]; then
        cp -r audit ${BACKUP_DIR}/
    fi

    # Backup state data
    if [ -d "data" ]; then
        cp -r data ${BACKUP_DIR}/
    fi

    # Create archive
    tar -czf ${BACKUP_DIR}.tar.gz ${BACKUP_DIR}
    rm -rf ${BACKUP_DIR}

    log_success "Backup created: ${BACKUP_DIR}.tar.gz"
}

# Show usage
show_usage() {
    cat << EOF
JML Engine Deployment Script

Usage: $0 [COMMAND] [OPTIONS]

Commands:
    build           Build Docker images
    deploy          Deploy using Docker Compose
    k8s-deploy      Deploy to Kubernetes
    health          Check service health
    backup          Create data backup
    logs            Show service logs
    restart         Restart services
    stop            Stop services
    cleanup         Remove stopped containers and images

Options:
    -e, --environment ENV    Deployment environment (development/production)
    -t, --tag TAG           Docker image tag (default: latest)
    -r, --registry REG      Docker registry (default: localhost:5000)

Examples:
    $0 build
    $0 deploy -e production
    $0 k8s-deploy
    $0 logs -f api

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -t|--tag)
            DOCKER_TAG="$2"
            shift 2
            ;;
        -r|--registry)
            DOCKER_REGISTRY="$2"
            shift 2
            ;;
        build)
            COMMAND="build"
            shift
            ;;
        deploy)
            COMMAND="deploy"
            shift
            ;;
        k8s-deploy)
            COMMAND="k8s-deploy"
            shift
            ;;
        health)
            COMMAND="health"
            shift
            ;;
        backup)
            COMMAND="backup"
            shift
            ;;
        logs)
            COMMAND="logs"
            shift
            ;;
        restart)
            COMMAND="restart"
            shift
            ;;
        stop)
            COMMAND="stop"
            shift
            ;;
        cleanup)
            COMMAND="cleanup"
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
case ${COMMAND:-deploy} in
    build)
        check_prerequisites
        build_images
        ;;
    deploy)
        check_prerequisites
        build_images
        deploy_compose
        ;;
    k8s-deploy)
        check_prerequisites
        build_images
        deploy_kubernetes
        ;;
    health)
        check_services_health
        ;;
    backup)
        backup_data
        ;;
    logs)
        if [ -n "$2" ]; then
            docker-compose logs -f $2
        else
            docker-compose logs -f
        fi
        ;;
    restart)
        docker-compose restart
        ;;
    stop)
        docker-compose down
        ;;
    cleanup)
        docker system prune -f
        docker volume prune -f
        ;;
    *)
        log_error "Unknown command: ${COMMAND}"
        show_usage
        exit 1
        ;;
esac

log_success "Operation completed successfully."
