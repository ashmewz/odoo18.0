#!/bin/bash
# =============================================================================
# moodle_patch.sh
# Pulls the latest Moodle 4.05 security patch, runs the upgrade, and sends
# success/failure/rollback signals to Azure Monitor Log Analytics.
#
# Usage:
#   1. Fill in WORKSPACE_ID and WORKSPACE_KEY from your Azure Log Analytics workspace.
#   2. Copy to vm-moodle: cp moodle_patch.sh /usr/local/bin/
#   3. Make executable:   chmod +x /usr/local/bin/moodle_patch.sh
#   4. Add to cron:       0 2 * * 0 /usr/local/bin/moodle_patch.sh >> /var/log/moodle_patch.log 2>&1
# =============================================================================

MOODLE_DIR=/var/www/html/moodle
WORKSPACE_ID="<YOUR_WORKSPACE_ID>"
WORKSPACE_KEY="<YOUR_PRIMARY_KEY>"
LOG_TYPE="MoodlePatchLog"

# -----------------------------------------------------------------------------
# Send a log entry to Azure Monitor Log Analytics
# Arguments: status, message, commit_hash
# -----------------------------------------------------------------------------
send_to_azure() {
    local status=$1
    local message=$2
    local commit=$3

    local body='[{"status":"'"$status"'","message":"'"$message"'","commit":"'"$commit"'","host":"vm-moodle"}]'
    local date=$(date -u +"%a, %d %b %Y %H:%M:%S GMT")
    local content_length=${#body}
    local string_to_sign="POST\n${content_length}\napplication/json\nx-ms-date:${date}\n/api/logs"
    local signature=$(echo -n "$string_to_sign" | openssl dgst -sha256 -hmac "$(echo $WORKSPACE_KEY | base64 -d)" -binary | base64)

    curl -s -X POST \
        "https://${WORKSPACE_ID}.ods.opinsights.azure.com/api/logs?api-version=2016-04-01" \
        -H "Authorization: SharedKey ${WORKSPACE_ID}:${signature}" \
        -H "Content-Type: application/json" \
        -H "Log-Type: ${LOG_TYPE}" \
        -H "x-ms-date: ${date}" \
        -d "$body"

    echo "[$(date)] Azure Monitor notified: $status — $message"
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
echo "========================================"
echo " Moodle Patch Script — $(date)"
echo "========================================"

# Step 1 — Save the current (last known good) commit hash
LAST_GOOD=$(git -C $MOODLE_DIR rev-parse HEAD)
echo "[INFO] Current commit: $LAST_GOOD"

# Step 2 — Pull latest security patch from Moodle 4.05 stable branch
echo "[INFO] Pulling latest patch from MOODLE_405_STABLE..."
git -C $MOODLE_DIR fetch origin
git -C $MOODLE_DIR pull origin MOODLE_405_STABLE

# Step 3 — Run Moodle upgrade
echo "[INFO] Running Moodle upgrade..."
sudo -u www-data php $MOODLE_DIR/admin/cli/upgrade.php --non-interactive
UPGRADE_EXIT=$?

# Step 4 — Check if upgrade succeeded
if [ $UPGRADE_EXIT -ne 0 ]; then
    echo "[ERROR] Upgrade failed. Triggering rollback..."

    # Notify Azure Monitor — fault detected
    send_to_azure "ROLLBACK_TRIGGERED" "Moodle upgrade failed. Rolling back to $LAST_GOOD." "$LAST_GOOD"

    # Rollback to last good commit
    git -C $MOODLE_DIR checkout $LAST_GOOD

    # Re-run upgrade on the rolled-back version
    sudo -u www-data php $MOODLE_DIR/admin/cli/upgrade.php --non-interactive

    # Notify Azure Monitor — rollback complete
    send_to_azure "ROLLBACK_COMPLETE" "Rollback to $LAST_GOOD completed successfully." "$LAST_GOOD"

    echo "[INFO] Rollback complete. Moodle restored to $LAST_GOOD."
else
    NEW_COMMIT=$(git -C $MOODLE_DIR rev-parse HEAD)
    echo "[INFO] Upgrade successful. New commit: $NEW_COMMIT"

    # Notify Azure Monitor — patch success
    send_to_azure "PATCH_SUCCESS" "Moodle patched successfully." "$NEW_COMMIT"
fi

echo "========================================"
echo " Done — $(date)"
echo "========================================"
