#!/bin/bash
# Example Usage Scenarios for Si5351A Control

# This file demonstrates various use cases for controlling the Si5351A
# frequency generator with individual clock output control.

# ============================================================================
# Basic Examples
# ============================================================================

echo "Example 1: Set frequency on CLK0 only"
echo "./si.sh freq 113000"
echo ""

echo "Example 2: Set frequency with CLK0 and CLK1 enabled"
echo "./si.sh freq 100000 clk0+clk1"
echo ""

# ============================================================================
# Output Control Examples
# ============================================================================

echo "Example 3: Enable/Disable Individual Outputs"
echo "./si.sh clk0 enable    # Enable CLK0"
echo "./si.sh clk0 disable   # Disable CLK0"
echo "./si.sh clk0 toggle    # Toggle CLK0 state"
echo "./si.sh clk1 enable    # Enable CLK1"
echo "./si.sh clk2 disable   # Disable CLK2"
echo ""

# ============================================================================
# Status and Verification
# ============================================================================

echo "Example 4: Check Current Status"
echo "./si.sh status         # Show which outputs are enabled"
echo "./si.sh crystal        # Check crystal lock status"
echo ""

# ============================================================================
# Advanced Combinations
# ============================================================================

echo "Example 5: Complete Configuration (Frequency + Output Control)"
echo "python3 pyftdi/bin/set_si5351.py --freq 113000 \\"
echo "  --clk0 enable --clk1-ctrl disable --clk2-ctrl enable"
echo ""

# ============================================================================
# Multi-Device Control
# ============================================================================

echo "Example 6: Multiple Devices on Same Bus"
echo "./si.sh freq 113000 --addr 0xC0    # First device"
echo "./si.sh freq 100000 --addr 0xC2    # Second device"
echo ""

# ============================================================================
# Testing with Dry-Run
# ============================================================================

echo "Example 7: Preview Changes Without Applying (Dry-Run)"
echo "./si.sh freq 113000 --dry-run"
echo "python3 pyftdi/bin/set_si5351.py --clk0 enable --dry-run"
echo ""

# ============================================================================
# Workflow: Complete Setup from Scratch
# ============================================================================

echo "Example 8: Complete Setup Workflow"
echo ""
echo "# Step 1: Configure frequency"
echo "./si.sh freq 113000 clk0+clk1"
echo ""
echo "# Step 2: Verify crystal is working"
echo "./si.sh crystal"
echo ""
echo "# Step 3: Check output state"
echo "./si.sh status"
echo ""
echo "# Step 4: Adjust outputs as needed"
echo "./si.sh clk1 disable"
echo ""
echo "# Step 5: Verify final configuration"
echo "./si.sh status"
echo ""

# ============================================================================
# Common Use Cases
# ============================================================================

echo "Example 9: Common Use Cases"
echo ""
echo "Case A: Single clock output (CLK0 only)"
echo "  ./si.sh freq 113000"
echo ""
echo "Case B: Test signal on CLK0, keep CLK1 disabled"
echo "  ./si.sh freq 1000000 clk0+clk1"
echo "  ./si.sh clk1 disable"
echo ""
echo "Case C: Multiple independent outputs on same frequency"
echo "  ./si.sh freq 50000 clk0+clk1"
echo "  ./si.sh clk2 enable"
echo ""
echo "Case D: Toggle specific output on/off"
echo "  ./si.sh clk0 toggle    # If CLK0 is on, turn it off; if off, turn it on"
echo ""

# ============================================================================
# Debugging and Troubleshooting
# ============================================================================

echo "Example 10: Debugging"
echo ""
echo "# See all register writes (debug output)"
echo "./si.sh freq 113000 2>&1 | grep DEBUG"
echo ""
echo "# Test with dry-run to see what would change"
echo "./si.sh clk0 enable --dry-run"
echo ""
echo "# Check I2C address conversion"
echo "python3 pyftdi/bin/set_si5351.py --addr 0xC0 --show-output"
echo ""
