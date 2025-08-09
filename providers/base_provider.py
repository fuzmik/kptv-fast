"""
Base Provider Class
Defines the interface that all streaming service providers must implement
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging
import sys

logger = logging.getLogger(__name__)

class BaseProvider(ABC):
    """Base class for all streaming service providers"""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"providers.{name}")
        # Set recursion limit to prevent stack overflow
        if sys.getrecursionlimit() < 2000:
            sys.setrecursionlimit(2000)
        
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
        try:
            required_fields = ['id', 'name', 'stream_url']
            
            for field in required_fields:
                if not channel.get(field):
                    self.logger.warning(f"Channel missing required field '{field}': {channel.get('name', 'Unknown')}")
                    return False
                    
            return True
        except Exception as e:
            self.logger.error(f"Error validating channel: {e}")
            return False
    
    def normalize_channel(self, channel: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize channel data to ensure consistent format
        
        Args:
            channel: Raw channel data
            
        Returns:
            Normalized channel dictionary
        """
        try:
            normalized = {}
            
            # Safely extract and convert values
            normalized['id'] = str(channel.get('id', '')) if channel.get('id') is not None else ''
            normalized['name'] = str(channel.get('name', '')).strip() if channel.get('name') is not None else ''
            normalized['stream_url'] = str(channel.get('stream_url', '')).strip() if channel.get('stream_url') is not None else ''
            
            # Optional fields
            if channel.get('logo'):
                normalized['logo'] = str(channel['logo']).strip()
                
            if channel.get('group'):
                normalized['group'] = str(channel['group']).strip()
            else:
                normalized['group'] = 'General'
                
            if channel.get('number') is not None:
                try:
                    normalized['number'] = int(channel['number'])
                except (ValueError, TypeError):
                    pass
                    
            if channel.get('description'):
                normalized['description'] = str(channel['description']).strip()
                
            if channel.get('language'):
                normalized['language'] = str(channel['language']).strip()
            else:
                normalized['language'] = 'en'
            
            # Remove empty strings except for required fields
            return {k: v for k, v in normalized.items() if v != '' or k in ['id', 'name', 'stream_url']}
            
        except Exception as e:
            self.logger.error(f"Error normalizing channel: {e}")
            return channel
    
    def validate_programme(self, programme: Dict[str, Any]) -> bool:
        """
        Validate that a programme has required fields
        
        Args:
            programme: Programme dictionary to validate
            
        Returns:
            True if programme is valid, False otherwise
        """
        try:
            required_fields = ['title', 'start', 'stop']
            
            for field in required_fields:
                if not programme.get(field):
                    self.logger.warning(f"Programme missing required field '{field}': {programme.get('title', 'Unknown')}")
                    return False
                    
            return True
        except Exception as e:
            self.logger.error(f"Error validating programme: {e}")
            return False
    
    def normalize_programme(self, programme: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize programme data to ensure consistent format
        
        Args:
            programme: Raw programme data
            
        Returns:
            Normalized programme dictionary
        """
        try:
            normalized = {}
            
            # Required fields
            normalized['title'] = str(programme.get('title', '')).strip() if programme.get('title') is not None else ''
            normalized['start'] = str(programme.get('start', '')).strip() if programme.get('start') is not None else ''
            normalized['stop'] = str(programme.get('stop', '')).strip() if programme.get('stop') is not None else ''
            
            # Optional fields
            if programme.get('description'):
                normalized['description'] = str(programme['description']).strip()
                
            if programme.get('category'):
                normalized['category'] = str(programme['category']).strip()
                
            if programme.get('episode'):
                normalized['episode'] = str(programme['episode']).strip()
            
            # Remove empty strings except for required fields
            return {k: v for k, v in normalized.items() if v != '' or k in ['title', 'start', 'stop']}
            
        except Exception as e:
            self.logger.error(f"Error normalizing programme: {e}")
            return programme
    
    def get_user_agent(self) -> str:
        """Get a standard user agent string"""
        return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    
    def get_timeout(self) -> tuple:
        """Get standard timeout values for requests (connect, read)"""
        return (15, 45)  # Increased timeout values