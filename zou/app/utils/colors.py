def rgb_to_hex(color):
    """
    Return the given color values as a #rrggbb string.
    """
    [red, green, blue] = color.split(",")
    return f"#{int(red):02x}{int(green):02x}{int(blue):02x}"
