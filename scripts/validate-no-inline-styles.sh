#!/bin/bash

# Validation Script: Check for Zero Inline Styles and JavaScript
# Purpose: Verify that all inline styles and JavaScript have been extracted
# Usage: ./scripts/validate-no-inline-styles.sh

set -e

echo "======================================"
echo "Frontend Refactoring Validation Script"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Initialize counters
total_violations=0

# 1. Check for inline style attributes
echo "1. Checking for inline style attributes..."
style_count=$(grep -r 'style=' web-app/templates/ --include="*.html" 2>/dev/null | wc -l)

if [ "$style_count" -eq 0 ]; then
    echo -e "${GREEN}✅ PASS${NC}: No inline style attributes found"
else
    echo -e "${RED}❌ FAIL${NC}: Found $style_count inline style attributes"
    echo "   Details:"
    grep -r 'style=' web-app/templates/ --include="*.html" -n 2>/dev/null | head -10
    if [ "$style_count" -gt 10 ]; then
        echo "   ... and $(($style_count - 10)) more"
    fi
    total_violations=$((total_violations + style_count))
fi
echo ""

# 2. Check for inline JavaScript event handlers
echo "2. Checking for inline JavaScript event handlers..."
js_count=$(grep -rE 'on(click|change|load|input|submit|focus|blur|keyup|keydown)=' web-app/templates/ --include="*.html" 2>/dev/null | wc -l)

if [ "$js_count" -eq 0 ]; then
    echo -e "${GREEN}✅ PASS${NC}: No inline JavaScript handlers found"
else
    echo -e "${RED}❌ FAIL${NC}: Found $js_count inline JavaScript handlers"
    echo "   Details:"
    grep -rE 'on(click|change|load|input|submit)=' web-app/templates/ --include="*.html" -n 2>/dev/null | head -10
    if [ "$js_count" -gt 10 ]; then
        echo "   ... and $(($js_count - 10)) more"
    fi
    total_violations=$((total_violations + js_count))
fi
echo ""

# 3. Check file naming consistency
echo "3. Checking file naming consistency..."
naming_errors=0

for template in web-app/templates/pages/*.html; do
    if [ ! -f "$template" ]; then
        continue
    fi

    basename=$(basename "$template" .html)
    css_file="web-app/static/css/pages/${basename}.css"

    if [ ! -f "$css_file" ]; then
        echo -e "${YELLOW}⚠️  WARNING${NC}: Missing CSS file for $basename.html"
        naming_errors=$((naming_errors + 1))
    fi
done

if [ "$naming_errors" -eq 0 ]; then
    echo -e "${GREEN}✅ PASS${NC}: All page templates have matching CSS files"
else
    echo -e "${YELLOW}⚠️  WARNING${NC}: $naming_errors page templates missing CSS files"
    echo "   (This may be expected if pages don't need custom styles)"
fi
echo ""

# 4. Check CSS organization
echo "4. Checking CSS file organization..."
orphan_css=0

# Check for orphan CSS files in root (should be in subdirectories)
for css_file in web-app/static/css/*.css; do
    if [ -f "$css_file" ]; then
        filename=$(basename "$css_file")
        # Exclude known legacy files that may still exist during migration
        if [ "$filename" != "tailwind.input.css" ] && [ "$filename" != "tailwind.output.css" ]; then
            echo -e "${YELLOW}⚠️  ORPHAN${NC}: $css_file should be in base/, components/, pages/, utilities/, or vendor/"
            orphan_css=$((orphan_css + 1))
        fi
    fi
done

if [ "$orphan_css" -eq 0 ]; then
    echo -e "${GREEN}✅ PASS${NC}: All CSS files are organized into subdirectories"
else
    echo -e "${YELLOW}⚠️  WARNING${NC}: $orphan_css CSS files in root directory (should be organized)"
fi
echo ""

# 5. Check for <script> tags with defer attribute
echo "5. Checking JavaScript loading strategy..."
script_no_defer=$(grep -r '<script src=' web-app/templates/ --include="*.html" 2>/dev/null | grep -v 'defer' | wc -l)

if [ "$script_no_defer" -eq 0 ]; then
    echo -e "${GREEN}✅ PASS${NC}: All script tags use defer attribute"
else
    echo -e "${YELLOW}⚠️  INFO${NC}: Found $script_no_defer script tags without defer attribute"
    echo "   Consider adding defer for better page load performance"
fi
echo ""

# Final Summary
echo "======================================"
echo "Validation Summary"
echo "======================================"
echo ""
echo "Inline Styles: $style_count"
echo "Inline JavaScript: $js_count"
echo "Total Violations: $total_violations"
echo ""

if [ "$total_violations" -eq 0 ]; then
    echo -e "${GREEN}🎉 SUCCESS${NC}: All validation checks passed!"
    echo ""
    echo "✅ Zero inline styles"
    echo "✅ Zero inline JavaScript handlers"
    echo "✅ Frontend refactoring complete"
    exit 0
else
    echo -e "${RED}❌ VALIDATION FAILED${NC}: $total_violations violations found"
    echo ""
    echo "Please fix the violations listed above before marking the refactoring complete."
    exit 1
fi
