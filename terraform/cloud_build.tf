# ==============================================================================
# Cloud Build - Serverless Container Build & Deployment to Artifact Registry
# Orchestrated by Terraform directly in Google Cloud (No local Docker/Podman required)
# ==============================================================================

# Ensure Cloud Build service accounts have write permission to Artifact Registry
resource "google_artifact_registry_repository_iam_member" "cloudbuild_sa_writer" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.docker_repo.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${data.google_project.project.number}@cloudbuild.gserviceaccount.com"

  depends_on = [
    google_artifact_registry_repository.docker_repo,
    google_project_service.apis["cloudbuild.googleapis.com"]
  ]
}

resource "google_artifact_registry_repository_iam_member" "compute_sa_writer" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.docker_repo.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"

  depends_on = [
    google_artifact_registry_repository.docker_repo,
    google_project_service.apis["cloudbuild.googleapis.com"]
  ]
}

# Ensure Compute default service account (used as Cloud Build execution identity) has access to Storage & Logs
resource "google_project_iam_member" "compute_sa_storage" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"

  depends_on = [google_project_service.apis["cloudbuild.googleapis.com"]]
}

resource "google_project_iam_member" "compute_sa_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"

  depends_on = [google_project_service.apis["cloudbuild.googleapis.com"]]
}

resource "google_project_iam_member" "compute_sa_builder" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.builder"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"

  depends_on = [google_project_service.apis["cloudbuild.googleapis.com"]]
}

# Execute container build in Google Cloud Build service
resource "terraform_data" "cloud_build_image" {
  triggers_replace = [
    var.image_tag,
    filesha1("${path.module}/../Dockerfile"),
    filesha1("${path.module}/../pyproject.toml"),
    filesha1("${path.module}/../frontend/package.json"),
    filesha1("${path.module}/../app/static/index.html")
  ]

  provisioner "local-exec" {
    working_dir = "${path.module}/.."
    command     = "gcloud builds submit --project=${var.project_id} --tag=${local.container_image} ."
  }

  depends_on = [
    google_project_service.apis["cloudbuild.googleapis.com"],
    google_project_service.apis["artifactregistry.googleapis.com"],
    google_artifact_registry_repository.docker_repo,
    google_artifact_registry_repository_iam_member.cloudbuild_sa_writer,
    google_artifact_registry_repository_iam_member.compute_sa_writer,
    google_project_iam_member.compute_sa_storage,
    google_project_iam_member.compute_sa_logs,
    google_project_iam_member.compute_sa_builder
  ]
}
