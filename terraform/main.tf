##############################################################################
# main.tf — Docker Provider (local unix socket)
# Mirrors docker-compose.yml but managed through Terraform.
##############################################################################

terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {
  # Connect to the local Docker daemon via unix socket (Linux / WSL2 / macOS).
  # On Windows-native Docker Desktop the socket is exposed at the same path
  # through the Docker Desktop WSL integration.
  host = "unix:///var/run/docker.sock"
}

##############################################################################
# NETWORK
##############################################################################

resource "docker_network" "ecommerce_net" {
  name   = "ecommerce-net"
  driver = "bridge"
}

##############################################################################
# IMAGES — build from local Dockerfiles
##############################################################################

resource "docker_image" "auth" {
  name = "ass4-5-auth:tf"
  build {
    context    = "${path.module}/../services/auth"
    dockerfile = "Dockerfile"
  }
  triggers = {
    src_hash = sha1(join("", [
      filesha1("${path.module}/../services/auth/main.py"),
      filesha1("${path.module}/../services/auth/requirements.txt"),
      filesha1("${path.module}/../services/auth/Dockerfile"),
    ]))
  }
}

resource "docker_image" "product" {
  name = "ass4-5-product:tf"
  build {
    context    = "${path.module}/../services/product"
    dockerfile = "Dockerfile"
  }
  triggers = {
    src_hash = sha1(join("", [
      filesha1("${path.module}/../services/product/main.py"),
      filesha1("${path.module}/../services/product/requirements.txt"),
      filesha1("${path.module}/../services/product/Dockerfile"),
    ]))
  }
}

resource "docker_image" "order" {
  name = "ass4-5-order:tf"
  build {
    context    = "${path.module}/../services/order"
    dockerfile = "Dockerfile"
  }
  triggers = {
    src_hash = sha1(join("", [
      filesha1("${path.module}/../services/order/main.py"),
      filesha1("${path.module}/../services/order/requirements.txt"),
      filesha1("${path.module}/../services/order/Dockerfile"),
    ]))
  }
}

resource "docker_image" "user" {
  name = "ass4-5-user:tf"
  build {
    context    = "${path.module}/../services/user"
    dockerfile = "Dockerfile"
  }
  triggers = {
    src_hash = sha1(join("", [
      filesha1("${path.module}/../services/user/main.py"),
      filesha1("${path.module}/../services/user/requirements.txt"),
      filesha1("${path.module}/../services/user/Dockerfile"),
    ]))
  }
}

resource "docker_image" "user_chat" {
  name = "ass4-5-user_chat:tf"
  build {
    context    = "${path.module}/../services/user_chat"
    dockerfile = "Dockerfile"
  }
  triggers = {
    src_hash = sha1(join("", [
      filesha1("${path.module}/../services/user_chat/main.py"),
      filesha1("${path.module}/../services/user_chat/requirements.txt"),
      filesha1("${path.module}/../services/user_chat/Dockerfile"),
    ]))
  }
}

# Public images — pulled from Docker Hub
resource "docker_image" "postgres" {
  name         = "postgres:15-alpine"
  keep_locally = true
}

resource "docker_image" "nginx" {
  name         = "nginx:alpine"
  keep_locally = true
}

resource "docker_image" "prometheus" {
  name         = "prom/prometheus:latest"
  keep_locally = true
}

resource "docker_image" "grafana" {
  name         = "grafana/grafana:latest"
  keep_locally = true
}

##############################################################################
# POSTGRES
##############################################################################

resource "docker_container" "postgres" {
  name  = "postgres"
  image = docker_image.postgres.image_id

  # Optimise for low-RAM VDS (mirrors docker-compose command:)
  command = [
    "postgres",
    "-c", "shared_buffers=64MB",
    "-c", "work_mem=4MB",
    "-c", "effective_cache_size=128MB",
    "-c", "max_connections=50",
  ]

  env = [
    "POSTGRES_USER=${var.postgres_user}",
    "POSTGRES_PASSWORD=${var.postgres_password}",
    "POSTGRES_DB=${var.postgres_db}",
  ]

  networks_advanced {
    name = docker_network.ecommerce_net.name
  }

  # Memory limit (bytes): 300 MB
  memory = 300

  healthcheck {
    test         = ["CMD-SHELL", "pg_isready -U ${var.postgres_user} -d ${var.postgres_db}"]
    interval     = "10s"
    timeout      = "5s"
    retries      = 5
    start_period = "5s"
  }

  restart = "unless-stopped"
}

##############################################################################
# AUTH SERVICE
##############################################################################

resource "docker_container" "auth" {
  name  = "auth-service"
  image = docker_image.auth.image_id

  env = [
    "DATABASE_URL=postgresql+asyncpg://${var.postgres_user}:${var.postgres_password}@postgres:5432/${var.postgres_db}",
    "SECRET_KEY=${var.secret_key}",
  ]

  networks_advanced {
    name = docker_network.ecommerce_net.name
  }

  memory = 100
  restart = "unless-stopped"

  healthcheck {
    test         = ["CMD-SHELL", "curl -sf http://localhost:8000/health || exit 1"]
    interval     = "15s"
    timeout      = "5s"
    retries      = 3
    start_period = "10s"
  }

  depends_on = [docker_container.postgres]
}

##############################################################################
# PRODUCT SERVICE
##############################################################################

resource "docker_container" "product" {
  name  = "product-service"
  image = docker_image.product.image_id

  env = [
    "DATABASE_URL=postgresql+asyncpg://${var.postgres_user}:${var.postgres_password}@postgres:5432/${var.postgres_db}",
  ]

  networks_advanced {
    name = docker_network.ecommerce_net.name
  }

  memory = 100
  restart = "unless-stopped"

  healthcheck {
    test         = ["CMD-SHELL", "curl -sf http://localhost:8000/health || exit 1"]
    interval     = "15s"
    timeout      = "5s"
    retries      = 3
    start_period = "10s"
  }

  depends_on = [docker_container.postgres]
}

##############################################################################
# ORDER SERVICE
##############################################################################

resource "docker_container" "order" {
  name  = "order-service"
  image = docker_image.order.image_id

  env = [
    "DATABASE_URL=postgresql+asyncpg://${var.postgres_user}:${var.postgres_password}@postgres:5432/${var.postgres_db}",
  ]

  networks_advanced {
    name = docker_network.ecommerce_net.name
  }

  memory = 100
  restart = "unless-stopped"

  healthcheck {
    test         = ["CMD-SHELL", "curl -sf http://localhost:8000/health || exit 1"]
    interval     = "15s"
    timeout      = "5s"
    retries      = 3
    start_period = "10s"
  }

  depends_on = [docker_container.postgres]
}

##############################################################################
# USER SERVICE  (profile store, validates JWT from auth)
##############################################################################

resource "docker_container" "user" {
  name  = "user-service"
  image = docker_image.user.image_id

  env = [
    "DATABASE_URL=postgresql+asyncpg://${var.postgres_user}:${var.postgres_password}@postgres:5432/${var.postgres_db}",
    "SECRET_KEY=${var.secret_key}",
  ]

  networks_advanced {
    name = docker_network.ecommerce_net.name
  }

  memory = 100
  restart = "unless-stopped"

  healthcheck {
    test         = ["CMD-SHELL", "curl -sf http://localhost:8000/health || exit 1"]
    interval     = "15s"
    timeout      = "5s"
    retries      = 3
    start_period = "10s"
  }

  depends_on = [docker_container.postgres]
}

##############################################################################
# USER-CHAT SERVICE  (WebSocket chat + legacy profile REST)
##############################################################################

resource "docker_container" "user_chat" {
  name  = "user-chat-service"
  image = docker_image.user_chat.image_id

  env = [
    "DATABASE_URL=postgresql+asyncpg://${var.postgres_user}:${var.postgres_password}@postgres:5432/${var.postgres_db}",
  ]

  networks_advanced {
    name = docker_network.ecommerce_net.name
  }

  memory = 100
  restart = "unless-stopped"

  healthcheck {
    test         = ["CMD-SHELL", "curl -sf http://localhost:8000/health || exit 1"]
    interval     = "15s"
    timeout      = "5s"
    retries      = 3
    start_period = "10s"
  }

  depends_on = [docker_container.postgres]
}

##############################################################################
# NGINX  (reverse proxy + static frontend)
##############################################################################

resource "docker_container" "nginx" {
  name  = "nginx-gateway"
  image = docker_image.nginx.image_id

  ports {
    internal = 80
    external = 80
  }

  volumes {
    host_path      = abspath("${path.module}/../nginx/nginx.conf")
    container_path = "/etc/nginx/nginx.conf"
    read_only      = true
  }

  volumes {
    host_path      = abspath("${path.module}/../nginx/html")
    container_path = "/usr/share/nginx/html"
    read_only      = true
  }

  networks_advanced {
    name = docker_network.ecommerce_net.name
  }

  memory = 50
  restart = "unless-stopped"

  healthcheck {
    test         = ["CMD-SHELL", "curl -sf http://localhost/health || exit 1"]
    interval     = "15s"
    timeout      = "5s"
    retries      = 3
    start_period = "5s"
  }

  depends_on = [
    docker_container.auth,
    docker_container.product,
    docker_container.order,
    docker_container.user,
    docker_container.user_chat,
  ]
}

##############################################################################
# PROMETHEUS
##############################################################################

resource "docker_container" "prometheus" {
  name  = "prometheus"
  image = docker_image.prometheus.image_id

  ports {
    internal = 9090
    external = 9090
  }

  volumes {
    host_path      = abspath("${path.module}/../prometheus/prometheus.yml")
    container_path = "/etc/prometheus/prometheus.yml"
    read_only      = true
  }

  volumes {
    host_path      = abspath("${path.module}/../prometheus/alert.rules.yml")
    container_path = "/etc/prometheus/alert.rules.yml"
    read_only      = true
  }

  networks_advanced {
    name = docker_network.ecommerce_net.name
  }

  memory = 250
  restart = "unless-stopped"
}

##############################################################################
# GRAFANA
##############################################################################

resource "docker_container" "grafana" {
  name  = "grafana"
  image = docker_image.grafana.image_id

  ports {
    internal = 3000
    external = 3000
  }

  volumes {
    host_path      = abspath("${path.module}/../grafana/datasources.yml")
    container_path = "/etc/grafana/provisioning/datasources/datasources.yml"
    read_only      = true
  }

  env = [
    "GF_SECURITY_ADMIN_PASSWORD=${var.grafana_admin_password}",
  ]

  networks_advanced {
    name = docker_network.ecommerce_net.name
  }

  memory = 200
  restart = "unless-stopped"
}
