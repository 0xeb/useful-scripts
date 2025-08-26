#!/usr/bin/env python3
import os

def main():
    print("test_tool1.py executed successfully.")
    # Fetch environment variables
    img_idx = os.environ.get("QSS_IMG_IDX", "N/A")
    img_total = os.environ.get("QSS_IMG_TOTAL", "N/A")
    img_name = os.environ.get("QSS_IMG_NAME", "N/A")
    full_path = os.environ.get("QSS_FULL_PATH", "N/A")
    img_size = os.environ.get("QSS_IMG_SIZE", "N/A")
    file_size = os.environ.get("QSS_FILE_SIZE", "N/A")
    progress_percent = os.environ.get("QSS_PROGRESS_PERCENT", "N/A")

    print("Current image information:")
    print(f"  Index: {img_idx} of {img_total}")
    print(f"  Name: {img_name}")
    print(f"  Full path: {full_path}")
    print(f"  Size: {img_size}")
    print(f"  File size: {file_size}")
    print(f"  Progress: {progress_percent}%")
if __name__ == "__main__":
    main()
