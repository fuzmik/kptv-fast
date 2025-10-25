"""
Utility functions for cleaning M3U channel data.
"""

import re

def clean_tvg_name_value(tvg_name_value: str) -> str:
    """
    Removes leading numbers and whitespace from a value intended for tvg-name.

    Example:
        "104 Xumo Free Horror & Thriller Movies" -> "Xumo Free Horror & Thriller Movies"
        "  55 BBC News" -> "BBC News"
        "Channel Name" -> "Channel Name"
    """
    if not tvg_name_value:
        return ""
    
    # Use regex to remove leading digits and any subsequent whitespace
    # ^     : matches the beginning of the string
    # \d+  : matches one or more digits
    # \s*  : matches zero or more whitespace characters
    cleaned_value = re.sub(r'^\d+\s*', '', tvg_name_value)
    
    # Return the cleaned value, stripping any leading/trailing whitespace that might remain
    return cleaned_value.strip()

if __name__ == '__main__':
    # Example usage:
    test_values = [
        "104 Xumo Free Horror & Thriller Movies",
        "  55 BBC News",
        "Channel Name",
        "99",
        "  ",
        "",
        "1 ABC",
        "2-Channel",
        "3 Channel With Hyphen"
    ]
    
    for value in test_values:
        print(f"Original: '{value}' -> Cleaned: '{clean_tvg_name_value(value)}'")