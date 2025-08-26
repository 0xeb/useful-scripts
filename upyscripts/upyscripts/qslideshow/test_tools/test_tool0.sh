#!/bin/bash
# Example tool 0: Display current image information
echo "Current image information:"
echo "  Index: $QSS_IMG_IDX of $QSS_IMG_TOTAL"
echo "  Name: $QSS_IMG_NAME"
echo "  Full path: $QSS_FULL_PATH"
echo "  Size: $QSS_IMG_SIZE"
echo "  File size: $QSS_FILE_SIZE"
echo "  Progress: $QSS_PROGRESS_PERCENT%"

# Return 0 to keep image in list
exit 0