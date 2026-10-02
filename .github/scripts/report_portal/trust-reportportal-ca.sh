#!/usr/bin/env bash
# Mirrored from Quantinuum/mushroom's .github/scripts/report_portal/trust-reportportal-ca.sh
# so qnexus's own CI can trust the private ReportPortal host without a cross-repo checkout.
set -euo pipefail

: "${REPORTPORTAL_ENDPOINT:?REPORTPORTAL_ENDPOINT is required}"
: "${REPORTPORTAL_IP:?REPORTPORTAL_IP is required}"
: "${QUANTINUUM_CA_PUBLIC_KEY:?QUANTINUUM_CA_PUBLIC_KEY is required}"
: "${REPORTPORTAL_CA_CERT:?REPORTPORTAL_CA_CERT is required}"

reportportal_host="${REPORTPORTAL_ENDPOINT#*://}"
reportportal_host="${reportportal_host%%/*}"

echo "${REPORTPORTAL_IP} ${reportportal_host}" | sudo tee -a /etc/hosts
printf '%s\n' "${QUANTINUUM_CA_PUBLIC_KEY}" | sudo tee "${REPORTPORTAL_CA_CERT}" > /dev/null
sudo update-ca-certificates
