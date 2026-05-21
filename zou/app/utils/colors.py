def rgb_to_hex(color):
    """
    Return color as #rrggbb for the given color values.
    """
    [red, green, blue] = color.split(",")
    return f"#{int(red):02x}{int(green):02x}{int(blue):02x}"
