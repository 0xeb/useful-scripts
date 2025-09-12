#!/usr/bin/env python3
"""
Action history management for qslideshow.
Provides undo/redo functionality for actions.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, List, Optional, Any, Dict
from collections import deque
from .actions import UndoableAction, Action

if TYPE_CHECKING:
    from .core import SlideshowContext


class ActionHistory:
    """Manages action history for undo/redo functionality."""
    
    def __init__(self, max_history: int = 50):
        self.history: deque[UndoableAction] = deque(maxlen=max_history)
        self.redo_stack: List[UndoableAction] = []
        self.max_history = max_history
    
    def execute(self, action: UndoableAction, context: SlideshowContext, **kwargs) -> Any:
        """
        Execute action and add to history.
        
        Args:
            action: The undoable action to execute
            context: The slideshow context
            **kwargs: Additional arguments for the action
            
        Returns:
            Result from action execution
        """
        result = action.execute(context, **kwargs)
        self.history.append(action)
        self.redo_stack.clear()  # Clear redo stack on new action
        return result
    
    def undo(self, context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        """
        Undo last action.
        
        Args:
            context: The slideshow context
            **kwargs: Additional arguments for the undo action
            
        Returns:
            Result dictionary with undo status
        """
        if not self.history:
            return {"success": False, "error": "Nothing to undo"}
        
        action = self.history.pop()
        undo_action = action.get_undo_action()
        
        if undo_action:
            result = undo_action.execute(context, **kwargs)
            self.redo_stack.append(action)
            return {"success": True, "undone": action.name, "result": result}
        
        return {"success": False, "error": f"Action '{action.name}' cannot be undone"}
    
    def redo(self, context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        """
        Redo previously undone action.
        
        Args:
            context: The slideshow context
            **kwargs: Additional arguments for the action
            
        Returns:
            Result dictionary with redo status
        """
        if not self.redo_stack:
            return {"success": False, "error": "Nothing to redo"}
        
        action = self.redo_stack.pop()
        result = action.execute(context, **kwargs)
        self.history.append(action)
        return {"success": True, "redone": action.name, "result": result}
    
    def can_undo(self) -> bool:
        """Check if undo is available."""
        return len(self.history) > 0
    
    def can_redo(self) -> bool:
        """Check if redo is available."""
        return len(self.redo_stack) > 0
    
    def clear(self):
        """Clear all history."""
        self.history.clear()
        self.redo_stack.clear()
    
    def get_history_info(self) -> Dict[str, Any]:
        """
        Get information about current history state.
        
        Returns:
            Dictionary with history information
        """
        return {
            "history_count": len(self.history),
            "redo_count": len(self.redo_stack),
            "max_history": self.max_history,
            "can_undo": self.can_undo(),
            "can_redo": self.can_redo(),
            "last_action": self.history[-1].name if self.history else None,
            "next_redo": self.redo_stack[-1].name if self.redo_stack else None
        }
    
    def get_recent_actions(self, count: int = 10) -> List[str]:
        """
        Get names of recent actions.
        
        Args:
            count: Number of recent actions to return
            
        Returns:
            List of action names
        """
        recent = []
        for i in range(min(count, len(self.history))):
            idx = -(i + 1)
            recent.append(self.history[idx].name)
        return recent


class UndoAction(Action):
    """Action to undo the last undoable action."""
    
    def __init__(self, history: ActionHistory):
        super().__init__("undo", "Undo last action")
        self.history = history
    
    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        return self.history.undo(slideshow_context, **kwargs)


class RedoAction(Action):
    """Action to redo the last undone action."""
    
    def __init__(self, history: ActionHistory):
        super().__init__("redo", "Redo last undone action")
        self.history = history
    
    def execute(self, slideshow_context: SlideshowContext, **kwargs) -> Dict[str, Any]:
        return self.history.redo(slideshow_context, **kwargs)