#!/bin/bash
# Convert SVG icons to PNG format for WeChat miniprogram tabBar
# Generates both normal (gray) and active (green) versions

SIZE=81
GRAY_COLOR='#666666'
GREEN_COLOR='#2E7D32'

echo "Converting icons to ${SIZE}x${SIZE} PNG format..."
echo "Normal color: ${GRAY_COLOR}, Active color: ${GREEN_COLOR}"
echo

# Function to convert SVG to PNG with color replacement
convert_icon() {
    local svg_file=$1
    local output_file=$2
    local color=$3

    # Read SVG and replace colors
    sed -e "s/stroke=\"[^\"]*\"/stroke=\"${color}\"/g" \
        -e "s/fill=\"\([^n]\)/fill=\"${color}\"/g" \
        "${svg_file}" > "${output_file}.tmp.svg"

    # Convert to PNG
    rsvg-convert -w ${SIZE} -h ${SIZE} "${output_file}.tmp.svg" -o "${output_file}"

    # Clean up temp file
    rm "${output_file}.tmp.svg"

    echo "✓ Created ${output_file}"
}

# Convert calendar icon (today)
convert_icon "calendar.svg" "tab-today.png" "${GRAY_COLOR}"
convert_icon "calendar.svg" "tab-today-active.png" "${GREEN_COLOR}"

# Convert chart icon (trends)
convert_icon "chart.svg" "tab-trend.png" "${GRAY_COLOR}"
convert_icon "chart.svg" "tab-trend-active.png" "${GREEN_COLOR}"

# Convert settings icon
convert_icon "settings.svg" "tab-settings.png" "${GRAY_COLOR}"
convert_icon "settings.svg" "tab-settings-active.png" "${GREEN_COLOR}"

echo
echo "✓ All icons converted successfully!"
echo
echo "Generated files:"
ls -lh tab-*.png | awk '{print "  " $9 " (" $5 ")"}'
