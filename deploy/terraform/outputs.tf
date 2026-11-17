output "owner_url" {
  value = local.environment.PARKING_BASE_URL
}
output "viewer_url" {
  value = local.environment.PARKING_SHARE_BASE_URL
}
output "data_volume" {
  value = docker_volume.data.name
}
