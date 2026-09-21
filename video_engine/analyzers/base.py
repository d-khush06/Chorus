from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import numpy as np

class BaseAnalyzer(ABC):
    """
    Interface for all video analyzers.
    Receives frames sequentially and returns results on finalize().
    """
    
    @classmethod
    def is_available(cls) -> bool:
        """Return True if the analyzer has all required dependencies/models."""
        return True
        
    @classmethod
    def get_limitations(cls) -> str:
        """Return a string describing limitations (e.g. 'requires models.lock.json', 'GPU recommended')."""
        return "None"
        
    @property
    def name(self) -> str:
        return self.__class__.__name__
        
    def __init__(self, **kwargs):
        self.params = kwargs
        
    @abstractmethod
    def on_frame(self, frame: np.ndarray, ts: float, frame_idx: int):
        """
        Process a single frame.
        :param frame: BGR numpy array
        :param ts: timestamp in seconds
        :param frame_idx: original frame index
        """
        pass
        
    @abstractmethod
    def finalize(self) -> Dict[str, Any]:
        """
        Called when the video stream ends.
        :return: dictionary containing the analyzer's results.
        """
        pass
