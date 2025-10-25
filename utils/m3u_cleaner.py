"""
Utility functions for cleaning M3U channel data.
"""

import re

def clean_m3u_channel_name(channel_name: str) -> str:
    """
    Removes leading numbers and whitespace from a channel name.

    Example:
        "104 Xumo Free Horror & Thriller Movies" -> "Xumo Free Horror & Thriller Movies"
        "  55 BBC News" -> "BBC News"
        "Channel Name" -> "Channel Name"
    """
    if not channel_name:
        return ""
    
    # Use regex to remove leading digits and any subsequent whitespace
    # ^     : matches the beginning of the string
    # \d+  : matches one or more digits
    # \s*  : matches zero or more whitespace characters
    cleaned_name = re.sub(r'^\d+\s*', '', channel_name)
    
    # Return the cleaned name, stripping any leading/trailing whitespace that might remain
    return cleaned_name.strip()

if __name__ == '__main__':
    # Example usage:
    test_names = [
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
    
    for name in test_names:
        print(f"Original: '{name}' -> Cleaned: '{clean_m3u_channel_name(name)}'")
