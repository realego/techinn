#!/usr/bin/env bash
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this deployment as root so both production document roots can be updated." >&2
  exit 1
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "${script_dir}/.." && pwd)"
build_root="${project_root}/out"
deploy_stamp="$(date +%Y%m%d-%H%M%S)"

cd "${project_root}"
npm run build

if [[ ! -d "${build_root}" ]]; then
  echo "Next.js export directory was not created: ${build_root}" >&2
  exit 1
fi

for production_root in /home/techinn.co.zw/public_html /home/my.techinn.co.zw/public_html; do
  if [[ ! -d "${production_root}" ]]; then
    echo "Production document root does not exist: ${production_root}" >&2
    exit 1
  fi

  owner_group="$(stat -c '%u:%g' "${production_root}")"
  site_root="$(dirname "${production_root}")"
  backup_root="${site_root}/deployment-backups"
  backup_path="${backup_root}/frontend-${deploy_stamp}"
  mkdir -p "${backup_path}"
  cp -a "${production_root}/." "${backup_path}/"
  rsync -a --delete "${build_root}/" "${production_root}/"
  chown -R "${owner_group}" "${production_root}"
  echo "Deployed ${production_root} (backup: ${backup_path})"
done
