#!/usr/bin/env python3
"""
Gesture detection and management for qslideshow.
Maps touch/mouse gestures to action names.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Dict, Optional, List, Tuple
from .config import ConfigManager
from .actions import action_registry
import time
import math

if TYPE_CHECKING:
    from .core import SlideshowContext


class GestureDetector:
    """Detects gestures from touch/mouse events."""
    
    def __init__(self):
        self.touch_start_time = 0
        self.touch_start_pos = (0, 0)
        self.touch_points = []
        self.last_tap_time = 0
        self.tap_count = 0
        
        # Gesture thresholds
        self.swipe_threshold = 50  # pixels
        self.long_press_duration = 0.5  # seconds
        self.double_tap_interval = 0.3  # seconds
        self.pinch_threshold = 30  # pixels change in distance
        
    def process_touch_event(self, event_type: str, touches: list) -> Optional[str]:
        """
        Process touch events and return detected gesture name.
        
        Args:
            event_type: 'touchstart', 'touchmove', 'touchend'
            touches: List of touch points, each with 'x', 'y', 'id'
            
        Returns:
            Gesture name if detected, None otherwise
        """
        current_time = time.time()
        
        if event_type == 'touchstart':
            self.touch_start_time = current_time
            if len(touches) > 0:
                self.touch_start_pos = (touches[0]['x'], touches[0]['y'])
            self.touch_points = touches.copy()
            
            # Check for multi-finger tap
            if len(touches) == 3:
                return 'three_finger_tap'
            elif len(touches) == 2:
                # Could be start of two-finger gesture
                pass
                
        elif event_type == 'touchmove':
            if len(self.touch_points) == 2 and len(touches) == 2:
                # Check for pinch gesture
                initial_distance = self._calculate_distance(
                    self.touch_points[0], self.touch_points[1]
                )
                current_distance = self._calculate_distance(
                    touches[0], touches[1]
                )
                
                if abs(current_distance - initial_distance) > self.pinch_threshold:
                    if current_distance > initial_distance:
                        return 'pinch_out'
                    else:
                        return 'pinch_in'
                
                # Check for two-finger swipe
                avg_delta_x = sum(t['x'] - p['x'] for t, p in zip(touches, self.touch_points)) / 2
                avg_delta_y = sum(t['y'] - p['y'] for t, p in zip(touches, self.touch_points)) / 2
                
                if abs(avg_delta_x) > self.swipe_threshold:
                    if avg_delta_x > 0:
                        return 'two_finger_swipe_right'
                    else:
                        return 'two_finger_swipe_left'
                elif abs(avg_delta_y) > self.swipe_threshold:
                    if avg_delta_y > 0:
                        return 'two_finger_swipe_down'
                    else:
                        return 'two_finger_swipe_up'
                        
        elif event_type == 'touchend':
            duration = current_time - self.touch_start_time
            
            if len(touches) == 0 and len(self.touch_points) == 1:
                # Single finger gesture
                if duration > self.long_press_duration:
                    return 'long_press'
                
                # Check for swipe
                if self.touch_points:
                    delta_x = self.touch_points[0]['x'] - self.touch_start_pos[0]
                    delta_y = self.touch_points[0]['y'] - self.touch_start_pos[1]
                    
                    if abs(delta_x) > self.swipe_threshold:
                        if delta_x > 0:
                            return 'swipe_right'
                        else:
                            return 'swipe_left'
                    elif abs(delta_y) > self.swipe_threshold:
                        if delta_y > 0:
                            return 'swipe_down'
                        else:
                            return 'swipe_up'
                    else:
                        # Check for tap/double tap
                        if current_time - self.last_tap_time < self.double_tap_interval:
                            self.tap_count += 1
                            if self.tap_count == 2:
                                self.tap_count = 0
                                return 'double_tap'
                        else:
                            self.tap_count = 1
                            self.last_tap_time = current_time
                            # Single tap is not returned immediately to allow for double tap
        
        return None
    
    def _calculate_distance(self, point1: Dict, point2: Dict) -> float:
        """Calculate distance between two touch points."""
        dx = point1['x'] - point2['x']
        dy = point1['y'] - point2['y']
        return math.sqrt(dx * dx + dy * dy)
    
    def process_mouse_event(self, event_type: str, x: int, y: int, button: int = 1) -> Optional[str]:
        """
        Process mouse events as single-touch gestures.
        
        Args:
            event_type: 'mousedown', 'mousemove', 'mouseup'
            x, y: Mouse coordinates
            button: Mouse button (1=left, 2=middle, 3=right)
            
        Returns:
            Gesture name if detected, None otherwise
        """
        # Convert mouse events to touch events
        if event_type == 'mousedown':
            touches = [{'x': x, 'y': y, 'id': 0}]
            return self.process_touch_event('touchstart', touches)
        elif event_type == 'mousemove':
            touches = [{'x': x, 'y': y, 'id': 0}]
            return self.process_touch_event('touchmove', touches)
        elif event_type == 'mouseup':
            return self.process_touch_event('touchend', [])
        
        return None


class GestureManager:
    """Maps detected gestures to action names."""
    
    def __init__(self, config: ConfigManager, context: str = 'web'):
        self.config = config
        self.context = context
        self.gesture_map: Dict[str, str] = {}  # gesture_name -> action_name
        self.detector = GestureDetector()
        self._build_gesture_map()
    
    def _build_gesture_map(self):
        """Build the gesture to action mapping from config."""
        # Load common gesture mappings
        common_gestures = self.config.get('gestures.common', {})
        for gesture, action_name in common_gestures.items():
            self.gesture_map[gesture] = action_name
        
        # Load context-specific gesture mappings
        context_gestures = self.config.get(f'gestures.{self.context}', {})
        for gesture, action_name in context_gestures.items():
            self.gesture_map[gesture] = action_name
    
    def handle_touch_event(self, event_type: str, touches: list, 
                          slideshow_context: Optional[SlideshowContext] = None) -> Optional[Dict]:
        """
        Process touch event and execute action if gesture detected.
        
        Args:
            event_type: Touch event type
            touches: List of touch points
            slideshow_context: The slideshow context to pass to actions
            
        Returns:
            Result dictionary from action execution, or None if no action
        """
        gesture = self.detector.process_touch_event(event_type, touches)
        if not gesture:
            return None
        
        action_name = self.gesture_map.get(gesture)
        if not action_name:
            return None
        
        action = action_registry.get(action_name)
        if not action:
            return None
        
        if not action.can_execute(self.context):
            return None
        
        if slideshow_context:
            return action.execute(slideshow_context)
        return None
    
    def handle_mouse_event(self, event_type: str, x: int, y: int, button: int = 1,
                          slideshow_context: Optional[SlideshowContext] = None) -> Optional[Dict]:
        """
        Process mouse event as gesture and execute action if detected.
        
        Args:
            event_type: Mouse event type
            x, y: Mouse coordinates
            button: Mouse button
            slideshow_context: The slideshow context to pass to actions
            
        Returns:
            Result dictionary from action execution, or None if no action
        """
        gesture = self.detector.process_mouse_event(event_type, x, y, button)
        if not gesture:
            return None
        
        action_name = self.gesture_map.get(gesture)
        if not action_name:
            return None
        
        action = action_registry.get(action_name)
        if not action:
            return None
        
        if not action.can_execute(self.context):
            return None
        
        if slideshow_context:
            return action.execute(slideshow_context)
        return None
    
    def get_action_for_gesture(self, gesture: str) -> Optional[str]:
        """Get action name for a given gesture."""
        return self.gesture_map.get(gesture)
    
    def get_gestures_for_action(self, action_name: str) -> List[str]:
        """Get all gestures mapped to an action."""
        return [g for g, action in self.gesture_map.items() if action == action_name]
    
    def update_mapping(self, gesture: str, action_name: str):
        """Update or add a gesture mapping."""
        self.gesture_map[gesture] = action_name
    
    def remove_mapping(self, gesture: str):
        """Remove a gesture mapping."""
        if gesture in self.gesture_map:
            del self.gesture_map[gesture]
    
    def get_all_mappings(self) -> Dict[str, str]:
        """Get all current gesture mappings."""
        return self.gesture_map.copy()
    
    def get_help_text(self) -> str:
        """Generate help text showing all gesture mappings."""
        help_lines = ["Touch Gestures:"]
        
        gesture_descriptions = {
            'swipe_left': 'Swipe left',
            'swipe_right': 'Swipe right',
            'swipe_up': 'Swipe up',
            'swipe_down': 'Swipe down',
            'double_tap': 'Double tap',
            'long_press': 'Long press',
            'pinch_in': 'Pinch in (zoom out)',
            'pinch_out': 'Pinch out (zoom in)',
            'two_finger_swipe_left': 'Two-finger swipe left',
            'two_finger_swipe_right': 'Two-finger swipe right',
            'two_finger_swipe_up': 'Two-finger swipe up',
            'two_finger_swipe_down': 'Two-finger swipe down',
            'three_finger_tap': 'Three-finger tap'
        }
        
        for gesture, action_name in self.gesture_map.items():
            action = action_registry.get(action_name)
            if action:
                gesture_desc = gesture_descriptions.get(gesture, gesture)
                help_lines.append(f"  {gesture_desc:<30} {action.description}")
        
        return '\n'.join(help_lines)
    
    def configure_thresholds(self, swipe_threshold: int = None, 
                            long_press_duration: float = None,
                            double_tap_interval: float = None,
                            pinch_threshold: int = None):
        """Configure gesture detection thresholds."""
        if swipe_threshold is not None:
            self.detector.swipe_threshold = swipe_threshold
        if long_press_duration is not None:
            self.detector.long_press_duration = long_press_duration
        if double_tap_interval is not None:
            self.detector.double_tap_interval = double_tap_interval
        if pinch_threshold is not None:
            self.detector.pinch_threshold = pinch_threshold