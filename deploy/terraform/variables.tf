variable "name" {
  description = "Prefix for Docker resources."
  type        = string
  default     = "curbwatch"
}
variable "image_name" {
  description = "Name assigned to the image built from this checkout."
  type        = string
  default     = "curbwatch:local"
}
variable "build_context" {
  description = "Optional absolute source directory; defaults to this checkout."
  type        = string
  default     = null
}
variable "listen_address" {
  description = "Host interface to publish. Keep loopback when a reverse proxy is on this host."
  type        = string
  default     = "127.0.0.1"
}
variable "api_port" {
  type    = number
  default = 8000
}
variable "viewer_port" {
  type    = number
  default = 8002
}
variable "environment" {
  description = "Nonsecret runtime configuration. Use secret_files for credentials instead."
  type        = map(string)
  default     = {}
}
variable "secret_files" {
  description = "Map of secret variable names (without _FILE) to existing absolute files on the Docker host. File contents are not read into Terraform state."
  type        = map(string)
  default     = {}
  validation {
    condition     = alltrue([for name, path in var.secret_files : can(regex("^[A-Z][A-Z0-9_]+$", name)) && startswith(path, "/")])
    error_message = "Use uppercase environment names and absolute host file paths."
  }
}
