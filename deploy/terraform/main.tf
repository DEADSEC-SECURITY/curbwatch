locals {
  source = coalesce(var.build_context, abspath("${path.module}/../.."))
  source_files = concat(
    tolist(fileset(local.source, "backend/**/*.py")),
    tolist(fileset(local.source, "backend/resources/*.json")),
    tolist(fileset(local.source, "frontend/src/**")),
    tolist(fileset(local.source, "frontend/scripts/**")),
    ["LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md", "frontend/public/favicon.svg", "frontend/public/manifest.webmanifest", "Dockerfile", "requirements.lock.txt", "frontend/package.json", "frontend/package-lock.json", "frontend/index.html", "frontend/shared.html", "frontend/vite.config.js"]
  )
  environment = merge({
    PARKING_DATA_DIR       = "/data"
    PARKING_HOST           = "0.0.0.0"
    PARKING_SHARE_HOST     = "0.0.0.0"
    PARKING_PORT           = tostring(var.api_port)
    PARKING_SHARE_PORT     = tostring(var.viewer_port)
    CELERY_BROKER_URL      = "redis://redis:6379/0"
    PARKING_BASE_URL       = "http://127.0.0.1:${var.api_port}"
    PARKING_SHARE_BASE_URL = "http://127.0.0.1:${var.viewer_port}"
    }, var.environment,
    { for name, path in var.secret_files : "${name}_FILE" => "/run/secrets/${name}" }
  )
}
resource "docker_image" "app" {
  name         = var.image_name
  keep_locally = true
  build {
    context = local.source
  }
  triggers = {
    source = sha256(join("", [for file in sort(local.source_files) : filesha256("${local.source}/${file}")]))
  }
}
resource "docker_image" "redis" {
  name = "redis:7-alpine"
}
resource "docker_network" "app" {
  name = var.name
}
resource "docker_volume" "data" {
  name = "${var.name}-data"
  lifecycle {
    prevent_destroy = true
  }
}
resource "docker_container" "redis" {
  name    = "${var.name}-redis"
  image   = docker_image.redis.image_id
  restart = "unless-stopped"
  networks_advanced {
    name    = docker_network.app.name
    aliases = ["redis"]
  }
  healthcheck {
    test     = ["CMD", "redis-cli", "ping"]
    interval = "5s"
    timeout  = "3s"
    retries  = 10
  }
  wait = true
}
resource "docker_container" "app" {
  for_each      = toset(["api", "viewer", "worker", "scheduler"])
  name          = "${var.name}-${each.key}"
  image         = docker_image.app.image_id
  command       = [each.key]
  restart       = "unless-stopped"
  env           = [for name, value in local.environment : "${name}=${value}"]
  security_opts = ["no-new-privileges:true"]
  depends_on    = [docker_container.redis]
  networks_advanced {
    name = docker_network.app.name
  }
  volumes {
    volume_name    = docker_volume.data.name
    container_path = "/data"
  }
  dynamic "volumes" {
    for_each = var.secret_files
    content {
      host_path      = volumes.value
      container_path = "/run/secrets/${volumes.key}"
      read_only      = true
    }
  }
  dynamic "ports" {
    for_each = contains(["api", "viewer"], each.key) ? [each.key == "api" ? var.api_port : var.viewer_port] : []
    content {
      internal = ports.value
      external = ports.value
      ip       = var.listen_address
    }
  }
}
