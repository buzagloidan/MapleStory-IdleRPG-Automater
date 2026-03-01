"""
Template Matcher - OpenCV-based template matching for detecting game UI elements.
"""
import os
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
import logging

import cv2
import numpy as np


class MatchResult:
    """Represents a template match result."""
    
    def __init__(self, name: str, x: int, y: int, width: int, height: int, confidence: float):
        self.name = name
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.confidence = confidence
        
        # Center point (useful for clicking)
        self.center_x = x + width // 2
        self.center_y = y + height // 2
    
    def __repr__(self):
        return f"MatchResult({self.name}, pos=({self.x}, {self.y}), conf={self.confidence:.2f})"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "center_x": self.center_x,
            "center_y": self.center_y,
            "confidence": self.confidence
        }


class TemplateMatcher:
    """
    Template matching engine using OpenCV.
    Supports loading templates from files and matching against screenshots.
    """
    
    def __init__(self, templates_dir: str = "templates", logger: Optional[logging.Logger] = None):
        """
        Initialize template matcher.
        
        Args:
            templates_dir: Directory containing template images
            logger: Optional logger instance
        """
        self.templates_dir = Path(templates_dir)
        self.logger = logger or logging.getLogger(__name__)
        
        # Template cache: name -> (image, grayscale)
        self._template_cache: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
        
        # Default matching parameters
        self.default_threshold = 0.85
        self.default_method = cv2.TM_CCOEFF_NORMED
    
    def load_template(self, name: str, subdir: str = "") -> Optional[np.ndarray]:
        """
        Load a template image from file.
        
        Args:
            name: Template name (without extension)
            subdir: Optional subdirectory within templates_dir
        
        Returns:
            Template image as numpy array, or None if not found
        """
        cache_key = f"{subdir}/{name}" if subdir else name
        
        # Check cache
        if cache_key in self._template_cache:
            return self._template_cache[cache_key][0]
        
        # Try different extensions
        base_path = self.templates_dir / subdir if subdir else self.templates_dir
        for ext in [".png", ".jpg", ".jpeg", ".bmp"]:
            filepath = base_path / f"{name}{ext}"
            if filepath.exists():
                img = cv2.imread(str(filepath))
                if img is not None:
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    self._template_cache[cache_key] = (img, gray)
                    self.logger.debug(f"Loaded template: {cache_key}")
                    return img
        
        self.logger.warning(f"Template not found: {cache_key}")
        return None
    
    def preload_templates(self, subdir: str = "") -> int:
        """
        Preload all templates from a directory.
        
        Args:
            subdir: Subdirectory to load from
        
        Returns:
            Number of templates loaded
        """
        base_path = self.templates_dir / subdir if subdir else self.templates_dir
        if not base_path.exists():
            self.logger.warning(f"Templates directory not found: {base_path}")
            return 0
        
        count = 0
        for filepath in base_path.iterdir():
            if filepath.suffix.lower() in [".png", ".jpg", ".jpeg", ".bmp"]:
                name = filepath.stem
                cache_key = f"{subdir}/{name}" if subdir else name
                if self.load_template(name, subdir) is not None:
                    count += 1
        
        self.logger.info(f"Preloaded {count} templates from {base_path}")
        return count
    
    def find(
        self,
        screen: np.ndarray,
        template_name: str,
        threshold: Optional[float] = None,
        subdir: str = "",
        use_grayscale: bool = True
    ) -> Optional[MatchResult]:
        """
        Find a single template in the screen.
        
        Args:
            screen: Screenshot to search in
            template_name: Name of template to find
            threshold: Minimum confidence threshold (0-1)
            subdir: Template subdirectory
            use_grayscale: Whether to use grayscale matching
        
        Returns:
            MatchResult if found, None otherwise
        """
        if threshold is None:
            threshold = self.default_threshold
        
        cache_key = f"{subdir}/{template_name}" if subdir else template_name
        
        # Load template if not cached
        if cache_key not in self._template_cache:
            if self.load_template(template_name, subdir) is None:
                return None
        
        template_color, template_gray = self._template_cache[cache_key]
        template = template_gray if use_grayscale else template_color
        
        # Convert screen to grayscale if needed
        if use_grayscale and len(screen.shape) == 3:
            screen_match = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        else:
            screen_match = screen
        
        # Check dimensions
        if template.shape[0] > screen_match.shape[0] or template.shape[1] > screen_match.shape[1]:
            self.logger.warning(f"Template {template_name} is larger than screen")
            return None
        
        # Perform template matching
        result = cv2.matchTemplate(screen_match, template, self.default_method)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        if max_val >= threshold:
            h, w = template.shape[:2]
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(f"Template {template_name} matched: {max_val:.3f} >= {threshold}")
            return MatchResult(
                name=template_name,
                x=max_loc[0],
                y=max_loc[1],
                width=w,
                height=h,
                confidence=max_val
            )
        
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"Template {template_name} best match {max_val:.3f} < threshold {threshold}")
        return None
    
    def find_all(
        self,
        screen: np.ndarray,
        template_name: str,
        threshold: Optional[float] = None,
        subdir: str = "",
        max_results: int = 10,
        min_distance: int = 10
    ) -> List[MatchResult]:
        """
        Find all instances of a template in the screen.
        
        Args:
            screen: Screenshot to search in
            template_name: Name of template to find
            threshold: Minimum confidence threshold
            subdir: Template subdirectory
            max_results: Maximum number of results
            min_distance: Minimum pixel distance between results
        
        Returns:
            List of MatchResult objects
        """
        if threshold is None:
            threshold = self.default_threshold
        
        cache_key = f"{subdir}/{template_name}" if subdir else template_name
        
        if cache_key not in self._template_cache:
            if self.load_template(template_name, subdir) is None:
                return []
        
        template_color, template_gray = self._template_cache[cache_key]
        
        # Use grayscale for matching
        if len(screen.shape) == 3:
            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        else:
            screen_gray = screen
        
        # Perform template matching
        result = cv2.matchTemplate(screen_gray, template_gray, self.default_method)
        
        # Find all locations above threshold
        locations = np.where(result >= threshold)
        h, w = template_gray.shape[:2]
        
        # Group nearby matches
        matches = []
        for pt in zip(*locations[::-1]):
            # Check if too close to existing match
            too_close = False
            for match in matches:
                dist = ((pt[0] - match.x) ** 2 + (pt[1] - match.y) ** 2) ** 0.5
                if dist < min_distance:
                    too_close = True
                    break
            
            if not too_close:
                confidence = result[pt[1], pt[0]]
                matches.append(MatchResult(
                    name=template_name,
                    x=pt[0],
                    y=pt[1],
                    width=w,
                    height=h,
                    confidence=float(confidence)
                ))
                
                if len(matches) >= max_results:
                    break
        
        # Sort by confidence
        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches
    
    def find_any(
        self,
        screen: np.ndarray,
        template_names: List[str],
        threshold: Optional[float] = None,
        subdir: str = ""
    ) -> Optional[MatchResult]:
        """
        Find any of the given templates (returns first match).
        
        Args:
            screen: Screenshot to search in
            template_names: List of template names to try
            threshold: Minimum confidence threshold
            subdir: Template subdirectory
        
        Returns:
            First MatchResult found, or None
        """
        for name in template_names:
            result = self.find(screen, name, threshold, subdir)
            if result is not None:
                return result
        return None
    
    def find_best(
        self,
        screen: np.ndarray,
        template_names: List[str],
        threshold: Optional[float] = None,
        subdir: str = ""
    ) -> Optional[MatchResult]:
        """
        Find the best matching template from a list.
        
        Args:
            screen: Screenshot to search in
            template_names: List of template names to try
            threshold: Minimum confidence threshold
            subdir: Template subdirectory
        
        Returns:
            MatchResult with highest confidence, or None
        """
        best_match = None
        for name in template_names:
            result = self.find(screen, name, threshold, subdir)
            if result is not None:
                if best_match is None or result.confidence > best_match.confidence:
                    best_match = result
        return best_match
    
    def wait_for(
        self,
        capture_func,
        template_name: str,
        timeout: float = 10.0,
        interval: float = 0.5,
        threshold: Optional[float] = None,
        subdir: str = ""
    ) -> Optional[MatchResult]:
        """
        Wait for a template to appear on screen.
        
        Args:
            capture_func: Function that returns current screen
            template_name: Template to wait for
            timeout: Maximum wait time in seconds
            interval: Time between checks
            threshold: Minimum confidence threshold
            subdir: Template subdirectory
        
        Returns:
            MatchResult when found, or None if timeout
        """
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            screen = capture_func()
            if screen is not None:
                result = self.find(screen, template_name, threshold, subdir)
                if result is not None:
                    return result
            time.sleep(interval)
        
        self.logger.warning(f"Timeout waiting for template: {template_name}")
        return None
    
    def create_template_from_screen(
        self,
        screen: np.ndarray,
        x: int,
        y: int,
        width: int,
        height: int,
        name: str,
        subdir: str = ""
    ) -> bool:
        """
        Create a new template from a region of the screen.
        
        Args:
            screen: Screenshot to extract from
            x, y: Top-left corner
            width, height: Region dimensions
            name: Name for the new template
            subdir: Subdirectory to save in
        
        Returns:
            True if saved successfully
        """
        # Extract region
        region = screen[y:y+height, x:x+width]
        
        # Ensure directory exists
        save_dir = self.templates_dir / subdir if subdir else self.templates_dir
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # Save template
        filepath = save_dir / f"{name}.png"
        success = cv2.imwrite(str(filepath), region)
        
        if success:
            self.logger.info(f"Created template: {filepath}")
            # Add to cache
            gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
            cache_key = f"{subdir}/{name}" if subdir else name
            self._template_cache[cache_key] = (region.copy(), gray)
        
        return success


# Quick test
if __name__ == "__main__":
    from logger import setup_logger
    
    log = setup_logger("matcher_test", "debug")
    matcher = TemplateMatcher(logger=log)
    
    # Test template loading
    print(f"Templates directory: {matcher.templates_dir.absolute()}")
    loaded = matcher.preload_templates()
    print(f"Loaded {loaded} templates")

