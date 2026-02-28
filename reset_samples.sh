#!/bin/bash
# Daily reset for FleetNests sample sites.
# Runs at 3:00 AM via /etc/cron.d/fleetnests-samples
set -euo pipefail
cd /home/richard/projects/fleetnests
/usr/bin/python3 seed_samples.py >> /var/log/fleetnests-sample-reset.log 2>&1
echo "$(date '+%Y-%m-%d %H:%M:%S') Sample sites reset complete" >> /var/log/fleetnests-sample-reset.log
