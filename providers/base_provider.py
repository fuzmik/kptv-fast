"""
Base Provider Class
Defines the interface that all streaming service providers must implement
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class BaseProvider(ABC):
    """Base class for all streaming service providers"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"providers.{name}")
        
    @abstractmethod
    def get_channels(self) -> List[Dict[str, Any]]:
        """
        Get list of available channels
        
        Returns:
            List of channel dictionaries with the following structure:
            {
                'id': str,           # Unique channel identifier
                'name': str,         # Channel display name
                'stream_url': str,   # Playback URL
                'logo': str,         # Logo URL (optional)
                'group': str,        # Channel category/group (optional)
                'number': int,       # Channel number (optional)
                'description': str,  # Channel description (optional)
                'language': str,     # Channel language (optional)
            }
        """
        pass
    
    @abstractmethod
    def get_epg_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get EPG (Electronic Program Guide) data for channels
        
        Returns:
            Dictionary mapping channel IDs to list of programme dictionaries:
            {
                'channel_id': [
                    {
                        'title': str,        # Programme title
                        'description': str,  # Programme description (optional)
                        'start': str,        # Start time in XMLTV format (YYYYMMDDHHMMSS +TZTZ)
                        'stop': str,         # End time in XMLTV format (YYYYMMDDHHMMSS +TZTZ)
                        'category': str,     # Programme category (optional)
                        'episode': str,      # Episode information (optional)
                    },
                    ...
                ]
            }
        """
        pass
    
    def validate_channel(self, channel: Dict[str, Any]) -> bool:
        """
        Validate that a channel has required fields
        
        Args:
            channel: Channel dictionary to validate
            
        Returns:
            True if channel is valid, False otherwise
        """
        required_fields = ['id', 'name', 'stream_url']
        
        for field in required_fields:
            if not channel.get(field):
                self.logger.warning(f"Channel missing required field '{field}': {channel}")
                return False
                
        return True
    
    def normalize_channel(self, channel: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize channel data to ensure consistent format
        
        Args:
            channel: Raw channel data
            
        Returns:
            Normalized channel dictionary
        """
        normalized = {
            'id': str(channel.get('id', '')),
            'name': str(channel.get('name', '')).strip(),
            'stream_url': str(channel.get('stream_url', '')).strip(),
            'logo': str(channel.get('logo', '')).strip() if channel.get('logo') else '',
            'group': str(channel.get('group', 'General')).strip(),
            'number': int(channel.get('number', 0)) if channel.get('number') else None,
            'description': str(channel.get('description', '')).strip() if channel.get('description') else '',
            'language': str(channel.get('language', 'en')).strip(),
        }
        
        # Remove empty strings
        return {k: v for k, v in normalized.items() if v != ''}
    
    def validate_programme(self, programme: Dict[str, Any]) -> bool:
        """
        Validate that a programme has required fields
        
        Args:
            programme: Programme dictionary to validate
            
        Returns:
            True if programme is valid, False otherwise
        """
        required_fields = ['title', 'start', 'stop']
        
        for field in required_fields:
            if not programme.get(field):
                self.logger.warning(f"Programme missing required field '{field}': {programme}")
                return False
                
        return True
    
    def normalize_programme(self, programme: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize programme data to ensure consistent format
        
        Args:
            programme: Raw programme data
            
        Returns:
            Normalized programme dictionary
        """
        normalized = {
            'title': str(programme.get('title', '')).strip(),
            'description': str(programme.get('description', '')).strip() if programme.get('description') else '',
            'start': str(programme.get('start', '')).strip(),
            'stop': str(programme.get('stop', '')).strip(),
            'category': str(programme.get('category', '')).strip() if programme.get('category') else '',
            'episode': str(programme.get('episode', '')).strip() if programme.get('episode') else '',
        }
        
        # Remove empty strings
        return {k: v for k, v in normalized.items() if v != ''}
    
    def get_user_agent(self) -> str:
        """Get a standard user agent string"""
        return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    
    def get_timeout(self) -> tuple:
        """Get standard timeout values for requests (connect, read)"""
        return (10, 30)