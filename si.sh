#!/bin/bash
# Convenience wrapper for Si5351A control

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/pyftdi/bin/set_si5351.py"
DEFAULT_ADDR="0xC0"
DEFAULT_URL="auto"

if [[ $# -eq 0 ]]; then
    echo "Si5351A Clock Control Convenience Wrapper"
    echo "============================================"
    echo ""
    echo "Usage: $0 <command> [args] [--addr 0xXX] [--url URL]"
    echo ""
    echo "Clock Control Commands:"
    echo "  clk0 enable|disable|toggle    Control CLK0 output"
    echo "  clk1 enable|disable|toggle    Control CLK1 output"  
    echo "  clk2 enable|disable|toggle    Control CLK2 output"
    echo "  status|show                   Show current output state"
    echo "  freq <Hz> [clk0|clk0+clk1]   Set frequency (default: CLK0 only)"
    echo ""
    echo "Optional Arguments:"
    echo "  --addr 0xXX                   I2C address (default: 0xC0)"
    echo "  --url ftdi://...|auto         FTDI URL (default: auto)"
    echo ""
    echo "Examples:"
    echo "  $0 clk0 enable"
    echo "  $0 freq 113000"
    echo "  $0 freq 100000 clk0+clk1"
    echo "  $0 clk0 enable --addr 0xC0"
    echo "  $0 status"
    exit 0
fi

# Default values
ADDR="$DEFAULT_ADDR"
URL="$DEFAULT_URL"

# Pass all arguments directly through, but extract addr and url
CMD="$1"
shift

ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --addr)
            ADDR="$2"
            shift 2
            ;;
        --url)
            URL="$2"
            shift 2
            ;;
        *)
            ARGS+=("$1")
            shift
            ;;
    esac
done

case "$CMD" in
    clk0)
        if [[ "${ARGS[0]}" =~ ^(enable|disable|toggle)$ ]]; then
            python3 "$PYTHON_SCRIPT" --url "$URL" --addr "$ADDR" --clk0 "${ARGS[0]}" "${ARGS[@]:1}"
        else
            echo "Error: Invalid CLK0 command: ${ARGS[0]}"
            echo "Use: enable, disable, or toggle"
            exit 1
        fi
        ;;
    clk1)
        if [[ "${ARGS[0]}" =~ ^(enable|disable|toggle)$ ]]; then
            python3 "$PYTHON_SCRIPT" --url "$URL" --addr "$ADDR" --clk1-ctrl "${ARGS[0]}" "${ARGS[@]:1}"
        else
            echo "Error: Invalid CLK1 command: ${ARGS[0]}"
            echo "Use: enable, disable, or toggle"
            exit 1
        fi
        ;;
    clk2)
        if [[ "${ARGS[0]}" =~ ^(enable|disable|toggle)$ ]]; then
            python3 "$PYTHON_SCRIPT" --url "$URL" --addr "$ADDR" --clk2-ctrl "${ARGS[0]}" "${ARGS[@]:1}"
        else
            echo "Error: Invalid CLK2 command: ${ARGS[0]}"
            echo "Use: enable, disable, or toggle"
            exit 1
        fi
        ;;
    status|show)
        python3 "$PYTHON_SCRIPT" --url "$URL" --addr "$ADDR" --show-output "${ARGS[@]}"
        ;;
    freq)
        if [[ -z "${ARGS[0]}" ]]; then
            echo "Error: Frequency value required"
            exit 1
        fi
        FREQ="${ARGS[0]}"
        CLK_SETUP="${ARGS[1]:-}"
        
        if [[ "$CLK_SETUP" == "clk0+clk1" ]]; then
            python3 "$PYTHON_SCRIPT" --url "$URL" --addr "$ADDR" --freq "$FREQ" --clk1 "${ARGS[@]:2}"
        else
            python3 "$PYTHON_SCRIPT" --url "$URL" --addr "$ADDR" --freq "$FREQ" "${ARGS[@]:1}"
        fi
        ;;
    crystal|check-crystal)
        python3 "$PYTHON_SCRIPT" --url "$URL" --addr "$ADDR" --check-crystal "${ARGS[@]}"
        ;;
    *)
        echo "Error: Unknown command: $CMD"
        echo "Run '$0' with no arguments for help"
        exit 1
        ;;
esac
