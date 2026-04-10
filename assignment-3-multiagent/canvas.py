import base64
from io import BytesIO
from PIL import Image, ImageDraw


class DigitalCanvas:
    """Simple RGB canvas with primitive drawing operations.

    Coordinates are 0-indexed with (0, 0) in the top-left corner. Callers are
    expected to keep coordinates within ``[0, width-1]`` and
    ``[0, height-1]``.
    """

    def __init__(self, width=200, height=200):
        self.width = width
        self.height = height
        self.image = Image.new("RGB", (width, height), "white")
        self.draw = ImageDraw.Draw(self.image)

    def reset(self, color: str = "white") -> None:
        """Clear the canvas to a solid background color (default: white)."""
        self.image = Image.new("RGB", (self.width, self.height), color)
        self.draw = ImageDraw.Draw(self.image)
        
    def draw_rectangle(self, x0: int, y0: int, x1: int, y1: int, color: str) -> str:
        self.draw.rectangle([x0, y0, x1, y1], fill=color)
        return f"Rectangle drawn from ({x0},{y0}) to ({x1},{y1}) in {color}."

    def draw_circle(self, x: int, y: int, radius: int, color: str) -> str:
        self.draw.ellipse([x-radius, y-radius, x+radius, y+radius], fill=color)
        return f"Circle drawn at ({x},{y}) with radius {radius} in {color}."

    def draw_line(self, x0: int, y0: int, x1: int, y1: int, width: int, color: str) -> str:
        self.draw.line([x0, y0, x1, y1], fill=color, width=width)
        return f"Line drawn from ({x0},{y0}) to ({x1},{y1}) with width {width} in {color}."
    
    def draw_triangle(self, x1: int, y1: int, x2: int, y2: int, x3: int, y3: int, color: str) -> str:
        """Draw a filled triangle given three vertices."""
        self.draw.polygon([(x1, y1), (x2, y2), (x3, y3)], fill=color)
        return (
            f"Triangle drawn with vertices "
            f"({x1},{y1}), ({x2},{y2}), ({x3},{y3}) in {color}."
        )

    def draw_square(self, x: int, y: int, size: int, color: str) -> str:
        """Draw a filled square centered at (x, y) with side length `size`."""
        half = size // 2
        x0, y0 = x - half, y - half
        x1, y1 = x + half, y + half
        self.draw.rectangle([x0, y0, x1, y1], fill=color)
        return (
            f"Square drawn centered at ({x},{y}) with size {size} in {color}."
        )
        
    def get_base64(self) -> str:
        buffered = BytesIO()
        self.image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode("utf-8")
        
    def save(self, filename: str):
        self.image.save(filename)
