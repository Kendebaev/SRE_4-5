##############################################################################
# outputs.tf
##############################################################################

output "frontend_url" {
  description = "NexShop frontend (Nginx)"
  value       = "http://localhost"
}

output "grafana_url" {
  description = "Grafana dashboard"
  value       = "http://localhost:3000"
}

output "prometheus_url" {
  description = "Prometheus UI"
  value       = "http://localhost:9090"
}

output "network_name" {
  description = "Docker network used by all containers"
  value       = docker_network.ecommerce_net.name
}

output "container_names" {
  description = "All managed container names"
  value = [
    docker_container.postgres.name,
    docker_container.auth.name,
    docker_container.product.name,
    docker_container.order.name,
    docker_container.user.name,
    docker_container.user_chat.name,
    docker_container.nginx.name,
    docker_container.prometheus.name,
    docker_container.grafana.name,
  ]
}
