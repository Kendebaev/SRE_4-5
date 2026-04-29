##############################################################################
# variables.tf
##############################################################################

variable "postgres_user" {
  description = "PostgreSQL superuser name"
  type        = string
  default     = "appuser"
}

variable "postgres_password" {
  description = "PostgreSQL superuser password"
  type        = string
  sensitive   = true
  default     = "supersecurepassword"
}

variable "postgres_db" {
  description = "Name of the default database"
  type        = string
  default     = "ecommerce_db"
}

variable "secret_key" {
  description = "JWT signing secret shared between Auth and User services"
  type        = string
  sensitive   = true
  default     = "default_secret"
}

variable "grafana_admin_password" {
  description = "Grafana admin password"
  type        = string
  sensitive   = true
  default     = "admin"
}
