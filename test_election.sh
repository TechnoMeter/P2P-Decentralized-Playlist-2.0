#!/bin/bash

# ============================================================
# Test Script: Weighted Bully Algorithm with Uptime Threshold
# ============================================================
# This script starts 5 nodes with staggered times to test
# the election algorithm with different uptimes.
#
# Users (alphabetical order):
#   alice < bob < charlie < david < eve
#
# Expected behavior with UPTIME_THRESHOLD=60s:
#   - If uptime difference > 60s, more stable node wins
#   - If uptime difference <= 60s, higher username wins
# ============================================================

PROJECT_DIR="/Users/tejesh/Downloads/DS/P2P-Decentralized-Playlist-2.0"
DELAY=20  # seconds between each node start

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}  Weighted Bully Algorithm - Test Script${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  - UPTIME_THRESHOLD: 60 seconds"
echo "  - Delay between nodes: ${DELAY} seconds"
echo ""
echo -e "${YELLOW}Nodes to be started:${NC}"
echo "  1. alice (will have highest uptime)"
echo "  2. bob"
echo "  3. charlie"
echo "  4. david"
echo "  5. eve (will have lowest uptime, highest username)"
echo ""
echo -e "${GREEN}Starting nodes...${NC}"
echo ""

# Function to open a new terminal with the command (macOS)
open_terminal() {
    local username=$1
    local password=$2
    local title="P2P - $username"

    osascript <<EOF
tell application "Terminal"
    do script "cd '$PROJECT_DIR' && python main.py $username $password"
    set custom title of front window to "$title"
end tell
EOF
}

# Start Alice (will have highest uptime)
echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} Starting ${YELLOW}alice${NC}..."
open_terminal "alice" "password1"
echo "  alice started. Uptime will be ~$((DELAY * 4))s when eve joins."
echo ""

sleep $DELAY

# Start Bob
echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} Starting ${YELLOW}bob${NC}..."
open_terminal "bob" "password2"
echo "  bob started. Uptime will be ~$((DELAY * 3))s when eve joins."
echo ""

sleep $DELAY

# Start Charlie
echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} Starting ${YELLOW}charlie${NC}..."
open_terminal "charlie" "password3"
echo "  charlie started. Uptime will be ~$((DELAY * 2))s when eve joins."
echo ""

sleep $DELAY

# Start David
echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} Starting ${YELLOW}david${NC}..."
open_terminal "david" "password4"
echo "  david started. Uptime will be ~${DELAY}s when eve joins."
echo ""

sleep $DELAY

# Start Eve (highest username, lowest uptime)
echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} Starting ${YELLOW}eve${NC}..."
open_terminal "eve" "password5"
echo "  eve started. Uptime: ~0s"
echo ""

echo -e "${BLUE}============================================================${NC}"
echo -e "${GREEN}All nodes started!${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""
echo -e "${YELLOW}Expected Uptimes:${NC}"
echo "  alice:   ~$((DELAY * 4))s (80s)"
echo "  bob:     ~$((DELAY * 3))s (60s)"
echo "  charlie: ~$((DELAY * 2))s (40s)"
echo "  david:   ~${DELAY}s (20s)"
echo "  eve:     ~0s"
echo ""
echo -e "${YELLOW}Expected Election Results:${NC}"
echo ""
echo "  With UPTIME_THRESHOLD=60s:"
echo ""
echo "  alice vs eve: 80s - 0s = 80s > 60s → alice wins (eve yields)"
echo "  alice vs bob: 80s - 60s = 20s < 60s → bob wins (higher username)"
echo ""
echo "  Prediction: bob should become host"
echo "    - alice has highest uptime but bob is within threshold"
echo "    - bob has higher username than alice"
echo "    - charlie, david, eve all yield to alice (uptime diff > 60s)"
echo "    - bob doesn't yield to alice (uptime diff = 20s < 60s)"
echo ""
echo -e "${BLUE}============================================================${NC}"
echo -e "${YELLOW}Test Scenarios to Try:${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""
echo "1. ${GREEN}Check initial host${NC}"
echo "   Look at the status bar in each window"
echo "   Expected: bob should be HOST"
echo ""
echo "2. ${GREEN}Kill the host (close bob's window)${NC}"
echo "   Watch election in other terminals"
echo "   Expected: alice should become host (most stable remaining)"
echo ""
echo "3. ${GREEN}Restart bob${NC}"
echo "   Run: python main.py bob password2"
echo "   bob rejoins with 0s uptime, should yield to alice"
echo ""
echo "4. ${GREEN}Wait 2 minutes, then kill alice${NC}"
echo "   By then, all uptimes will be within 60s of each other"
echo "   Expected: eve should win (highest username)"
echo ""
echo -e "${BLUE}============================================================${NC}"
