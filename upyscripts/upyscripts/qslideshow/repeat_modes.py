#!/usr/bin/env python3
"""
Repeat mode handling for qslideshow.
Provides different repeat behaviors for slideshow playback.
"""

from enum import Enum
import random
from typing import List, Dict, Any
from pathlib import Path


class RepeatMode(Enum):
    """Different repeat behaviors for slideshow."""
    NONE = "none"  # No repeat
    FIXED = "fixed"  # Repeat with same order
    SHUFFLE = "shuffle"  # Shuffle once, repeat that order
    SHUFFLE_EACH = "shuffle-each"  # Reshuffle on each cycle
    
    @classmethod
    def from_config(cls, value):
        """
        Parse repeat mode from config value.
        
        Args:
            value: Config value (bool, str)
            
        Returns:
            RepeatMode enum value
        """
        if value is False or value == "false" or value == "none":
            return cls.NONE
        elif value is True or value == "true" or value == "fixed":
            return cls.FIXED
        elif value == "shuffle":
            return cls.SHUFFLE
        elif value == "shuffle-each":
            return cls.SHUFFLE_EACH
        else:
            return cls.FIXED  # Default for unknown values
    
    def to_bool(self) -> bool:
        """Convert to boolean for backward compatibility."""
        return self != RepeatMode.NONE
    
    def should_shuffle_on_start(self) -> bool:
        """Check if images should be shuffled on start."""
        return self in (RepeatMode.SHUFFLE, RepeatMode.SHUFFLE_EACH)
    
    def should_shuffle_on_cycle(self) -> bool:
        """Check if images should be reshuffled on each cycle."""
        return self == RepeatMode.SHUFFLE_EACH


class RepeatHandler:
    """Manages repeat logic and shuffling behavior."""
    
    def __init__(self, mode: RepeatMode = RepeatMode.FIXED):
        self.mode = mode
        self.cycle_count = 0
        self.original_order: List[Path] = []
        self.shuffled_order: List[Path] = []
        self.current_cycle_order: List[Path] = []
    
    def initialize(self, image_paths: List[Path]) -> List[Path]:
        """
        Initialize with image list.
        
        Args:
            image_paths: Original list of image paths
            
        Returns:
            Initial order of images (possibly shuffled)
        """
        self.original_order = image_paths.copy()
        self.cycle_count = 0
        
        if self.mode == RepeatMode.SHUFFLE:
            # Shuffle once at start
            self.shuffled_order = image_paths.copy()
            random.shuffle(self.shuffled_order)
            self.current_cycle_order = self.shuffled_order.copy()
            return self.shuffled_order
        elif self.mode == RepeatMode.SHUFFLE_EACH:
            # Shuffle for first cycle
            shuffled = image_paths.copy()
            random.shuffle(shuffled)
            self.current_cycle_order = shuffled
            return shuffled
        else:
            # Keep original order
            self.current_cycle_order = image_paths.copy()
            return image_paths
    
    def on_cycle_complete(self, current_paths: List[Path]) -> tuple[List[Path], bool]:
        """
        Called when reaching end of image list.
        
        Args:
            current_paths: Current image path list
            
        Returns:
            Tuple of (new_order, should_restart)
        """
        self.cycle_count += 1
        
        if self.mode == RepeatMode.NONE:
            # No repeat, stay at end
            return current_paths, False
        elif self.mode == RepeatMode.FIXED:
            # Keep same order, restart from beginning
            return self.original_order, True
        elif self.mode == RepeatMode.SHUFFLE:
            # Use the same shuffled order
            return self.shuffled_order if self.shuffled_order else current_paths, True
        elif self.mode == RepeatMode.SHUFFLE_EACH:
            # Reshuffle on each cycle
            new_order = self.original_order.copy()
            random.shuffle(new_order)
            self.current_cycle_order = new_order
            return new_order, True
        
        return current_paths, False
    
    def should_repeat(self) -> bool:
        """Check if slideshow should repeat."""
        return self.mode != RepeatMode.NONE
    
    def get_mode(self) -> RepeatMode:
        """Get current repeat mode."""
        return self.mode
    
    def set_mode(self, mode: RepeatMode):
        """
        Set repeat mode.
        
        Args:
            mode: New repeat mode
        """
        self.mode = mode
    
    def get_cycle_count(self) -> int:
        """Get number of completed cycles."""
        return self.cycle_count
    
    def reset(self):
        """Reset cycle count and orders."""
        self.cycle_count = 0
        self.shuffled_order = []
        self.current_cycle_order = []
    
    def get_current_order(self) -> List[Path]:
        """Get current cycle's image order."""
        return self.current_cycle_order
    
    def toggle_mode(self) -> RepeatMode:
        """
        Toggle through repeat modes.
        
        Returns:
            New repeat mode
        """
        modes = list(RepeatMode)
        current_index = modes.index(self.mode)
        next_index = (current_index + 1) % len(modes)
        self.mode = modes[next_index]
        return self.mode
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current repeat handler status.
        
        Returns:
            Status dictionary
        """
        return {
            "mode": self.mode.value,
            "cycle_count": self.cycle_count,
            "should_repeat": self.should_repeat(),
            "original_count": len(self.original_order),
            "current_count": len(self.current_cycle_order)
        }