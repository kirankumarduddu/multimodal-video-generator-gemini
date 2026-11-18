<#
.SYNOPSIS
  Prepare a Google Cloud project for Multimodal Video Generator (Windows PowerShell).
.EXAMPLE
  .\scripts\setup-gcp.ps1 -Project my-project -Email me@example.com
  .\scripts\setup-gcp.ps1 -Project my-project -Email me@example.com -SkipGrant   # not an owner: ask your admin
#>
param(
  [Parameter(Mandatory = $true)][string]$Project,
  [Parameter(Mandatory = $true)][string]$Email,
  [string]$Bucket = "",
  [switch]$SkipGrant
)
$ErrorActionPreference = "Stop"
function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
  throw "gcloud CLI not found. Install it: https://cloud.google.com/sdk/docs/install"
}

Step "Sign in to the gcloud CLI (opens a browser)"
gcloud auth login --update-adc
gcloud config set project $Project

Step "Enable the Vertex AI API"
gcloud services enable aiplatform.googleapis.com --project $Project
if ($Bucket) { gcloud services enable storage.googleapis.com --project $Project }

if (-not $SkipGrant) {
  Step "Grant $Email the roles it needs (needs owner or IAM admin)"
  gcloud projects add-iam-policy-binding $Project --member="user:$Email" --role="roles/aiplatform.user" --condition=None | Out-Null
  gcloud projects add-iam-policy-binding $Project --member="user:$Email" --role="roles/serviceusage.serviceUsageConsumer" --condition=None | Out-Null
  if ($Bucket) {
    gcloud storage buckets add-iam-policy-binding "gs://$Bucket" --member="user:$Email" --role="roles/storage.objectAdmin" | Out-Null
  }
} else {
  Write-Host "Skipped. Ask an owner to run:`n  gcloud projects add-iam-policy-binding $Project --member=user:$Email --role=roles/aiplatform.user`n  gcloud projects add-iam-policy-binding $Project --member=user:$Email --role=roles/serviceusage.serviceUsageConsumer"
}

Step "Application Default Credentials for the mvg CLI (opens a browser)"
gcloud auth application-default login
gcloud auth application-default set-quota-project $Project

Step "Done. Now run: mvg doctor"
