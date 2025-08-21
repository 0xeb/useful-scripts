from datetime import datetime
from typing import Optional, Tuple

def find_latest_file_date(
    base_folder: str, 
    filter: str = '*.*'
) -> Optional[Tuple[datetime, str]]: ...