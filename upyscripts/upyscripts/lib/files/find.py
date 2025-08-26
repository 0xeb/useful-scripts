# by Elias Bachaalany (c) 2023
# Files search utility

import os
import fnmatch
from datetime import datetime
from typing import Optional, Tuple

def find_latest_file_date(base_folder: str, filter: str = '*.*') -> Optional[Tuple[datetime, str]]:
    """
    Recursively enumerate files in the given base folder and find the latest file date,
    filtering by the specified pattern (e.g., "*.md", "*.txt").
    
    Args:
        base_folder (str): The base directory to start the search.
        filter (str): The glob-style pattern to filter files by.
    
    Returns:
        Optional[Tuple[datetime, str]]: A tuple of the date of the latest file and its path,
        or None if no matching files are found.
    """
    latest_date = None
    latest_file = ''
    
    for root, _, files in os.walk(base_folder):
        for file in fnmatch.filter(files, filter):
            file_path = os.path.join(root, file)
            file_mtime = os.path.getmtime(file_path)
            file_date = datetime.fromtimestamp(file_mtime)
            
            if latest_date is None or file_date > latest_date:
                latest_date = file_date
                latest_file = file_path
                
    return (latest_date, latest_file) if latest_date else (None, None)
