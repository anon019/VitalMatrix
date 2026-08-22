#!/usr/bin/env python3
"""
Convert SVG icons to PNG format for WeChat miniprogram tabBar
Generates both normal (gray) and active (green) versions
"""
import cairosvg
from PIL import Image
import io
import re

# Icon configuration
ICONS = {
    'calendar.svg': 'tab-today',
    'chart.svg': 'tab-trend',
    'settings.svg': 'tab-settings'
}

# Colors
GRAY_COLOR = '#666666'  # Normal state
GREEN_COLOR = '#2E7D32'  # Active state
SIZE = 81  # 81x81 pixels

def change_svg_color(svg_content, color):
    """Change stroke and fill colors in SVG to specified color"""
    # Replace stroke colors
    svg_content = re.sub(r'stroke="[^"]*"', f'stroke="{color}"', svg_content)
    # Replace fill colors (but keep 'none')
    svg_content = re.sub(r'fill="(?!none)[^"]*"', f'fill="{color}"', svg_content)
    return svg_content

def svg_to_png(svg_file, output_file, color):
    """Convert SVG to PNG with specified color and size"""
    # Read SVG content
    with open(svg_file, 'r') as f:
        svg_content = f.read()

    # Change color
    svg_content = change_svg_color(svg_content, color)

    # Convert SVG to PNG
    png_data = cairosvg.svg2png(
        bytestring=svg_content.encode('utf-8'),
        output_width=SIZE,
        output_height=SIZE
    )

    # Save PNG
    with open(output_file, 'wb') as f:
        f.write(png_data)

    print(f"✓ Created {output_file}")

def main():
    print(f"Converting icons to {SIZE}x{SIZE} PNG format...")
    print(f"Normal color: {GRAY_COLOR}, Active color: {GREEN_COLOR}\n")

    for svg_file, base_name in ICONS.items():
        # Create normal version (gray)
        svg_to_png(svg_file, f'{base_name}.png', GRAY_COLOR)

        # Create active version (green)
        svg_to_png(svg_file, f'{base_name}-active.png', GREEN_COLOR)

    print("\n✓ All icons converted successfully!")
    print("\nGenerated files:")
    for base_name in ICONS.values():
        print(f"  - {base_name}.png (normal)")
        print(f"  - {base_name}-active.png (active)")

if __name__ == '__main__':
    main()
