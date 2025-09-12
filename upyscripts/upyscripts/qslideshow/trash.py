#!/usr/bin/env python3
"""
Trash management for qslideshow.
Provides safe file deletion with restore capability.
"""

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, List


class TrashManager:
    """Manages deleted files in trash folder with restore capability."""
    
    def __init__(self, base_path: Path, trash_dir_name: str = ".trash"):
        self.base_path = base_path
        self.trash_dir = base_path / trash_dir_name
        self.trash_dir.mkdir(exist_ok=True)
        self.manifest_file = self.trash_dir / 'manifest.json'
        self.manifest: Dict[str, Dict] = {}
        self.load_manifest()
    
    def load_manifest(self):
        """Load trash manifest from disk."""
        if self.manifest_file.exists():
            try:
                with open(self.manifest_file, 'r') as f:
                    self.manifest = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.manifest = {}
    
    def save_manifest(self):
        """Save trash manifest to disk."""
        with open(self.manifest_file, 'w') as f:
            json.dump(self.manifest, f, indent=2, default=str)
    
    def trash_file(self, file_path: Path) -> Path:
        """
        Move file to trash with unique name.
        
        Args:
            file_path: Path to file to trash
            
        Returns:
            Path to file in trash
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = f"{timestamp}_{id(file_path)}"
        unique_name = f"{unique_id}_{file_path.name}"
        trash_path = self.trash_dir / unique_name
        
        # Store metadata in manifest
        self.manifest[unique_name] = {
            'original_path': str(file_path.absolute()),
            'deleted_at': timestamp,
            'original_name': file_path.name,
            'size': file_path.stat().st_size if file_path.exists() else 0
        }
        
        # Move file to trash
        shutil.move(str(file_path), str(trash_path))
        self.save_manifest()
        return trash_path
    
    def restore_file(self, trash_name: str) -> Optional[Path]:
        """
        Restore file from trash to original location.
        
        Args:
            trash_name: Name of file in trash
            
        Returns:
            Path to restored file, or None if failed
        """
        if trash_name not in self.manifest:
            return None
        
        metadata = self.manifest[trash_name]
        original_path = Path(metadata['original_path'])
        trash_path = self.trash_dir / trash_name
        
        if not trash_path.exists():
            # File was permanently deleted from trash
            del self.manifest[trash_name]
            self.save_manifest()
            return None
        
        # Ensure parent directory exists
        original_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Handle naming conflicts
        if original_path.exists():
            # Add suffix to avoid overwriting
            base = original_path.stem
            suffix = original_path.suffix
            counter = 1
            while original_path.exists():
                original_path = original_path.parent / f"{base}_restored_{counter}{suffix}"
                counter += 1
        
        # Restore file
        shutil.move(str(trash_path), str(original_path))
        del self.manifest[trash_name]
        self.save_manifest()
        return original_path
    
    def cleanup_old_items(self, days: int = 30) -> int:
        """
        Remove items older than specified days from trash.
        
        Args:
            days: Number of days to keep items
            
        Returns:
            Number of items removed
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        items_to_remove = []
        
        for trash_name, metadata in self.manifest.items():
            deleted_at = datetime.strptime(metadata['deleted_at'], '%Y%m%d_%H%M%S')
            if deleted_at < cutoff_date:
                items_to_remove.append(trash_name)
        
        for trash_name in items_to_remove:
            trash_path = self.trash_dir / trash_name
            if trash_path.exists():
                trash_path.unlink()
            del self.manifest[trash_name]
        
        if items_to_remove:
            self.save_manifest()
        
        return len(items_to_remove)
    
    def empty_trash(self):
        """Permanently delete all items in trash."""
        for trash_name in list(self.manifest.keys()):
            trash_path = self.trash_dir / trash_name
            if trash_path.exists():
                trash_path.unlink()
        
        self.manifest.clear()
        self.save_manifest()
    
    def list_trash_items(self) -> List[Dict]:
        """
        List all items currently in trash.
        
        Returns:
            List of trash item metadata
        """
        items = []
        for trash_name, metadata in self.manifest.items():
            trash_path = self.trash_dir / trash_name
            items.append({
                'trash_name': trash_name,
                'original_name': metadata['original_name'],
                'original_path': metadata['original_path'],
                'deleted_at': metadata['deleted_at'],
                'size': metadata.get('size', 0),
                'exists': trash_path.exists()
            })
        return sorted(items, key=lambda x: x['deleted_at'], reverse=True)
    
    def get_trash_size(self) -> int:
        """
        Get total size of all items in trash.
        
        Returns:
            Total size in bytes
        """
        total_size = 0
        for trash_name in self.manifest.keys():
            trash_path = self.trash_dir / trash_name
            if trash_path.exists():
                total_size += trash_path.stat().st_size
        return total_size
    
    def restore_by_original_path(self, original_path: Path) -> Optional[Path]:
        """
        Restore most recently deleted file with given original path.
        
        Args:
            original_path: Original path of file to restore
            
        Returns:
            Path to restored file, or None if not found
        """
        # Find most recent item with matching original path
        matching_items = []
        for trash_name, metadata in self.manifest.items():
            if Path(metadata['original_path']) == original_path:
                matching_items.append((trash_name, metadata['deleted_at']))
        
        if not matching_items:
            return None
        
        # Sort by deletion time and get most recent
        matching_items.sort(key=lambda x: x[1], reverse=True)
        trash_name = matching_items[0][0]
        
        return self.restore_file(trash_name)