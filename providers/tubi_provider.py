"""
Tubi Provider Implementation
"""

import requests
import json
import uuid
import time
import os
from datetime import datetime
from typing import List, Dict, Any
from .base_provider import BaseProvider

class TubiProvider(BaseProvider):
    """Provider for Tubi TV channels"""
    
    def __init__(self):
        super().__init__("tubi")
        
        self.device_id = str(uuid.uuid4())
        self.access_token = None
        self.token_expires_at = 0
        
        self.headers = {
            'accept': '*/*',
            'accept-language': 'en-US',
            'content-type': 'application/json',
            'origin': 'https://tubitv.com',
            'referer': 'https://tubitv.com/',
            'user-agent': self.get_user_agent(),
        }
        
        # Try to get user credentials from environment
        self.user = os.getenv("TUBI_USER")
        self.password = os.getenv("TUBI_PASS")
    
    def _get_access_token(self) -> str:
        """Get or refresh access token"""
        if self.access_token and time.time() < self.token_expires_at:
            return self.access_token
        
        try:
            if self.user and self.password:
                # Use authenticated login
                url = 'https://account.production-public.tubi.io/user/login'
                json_data = {
                    'type': 'email',
                    'platform': 'web',
                    'device_id': self.device_id,
                    'credentials': {
                        'email': self.user,
                        'password': self.password
                    },
                    'errorLog': False,
                }
            else:
                # Use anonymous token
                url = 'https://account.production-public.tubi.io/device/anonymous/token'
                json_data = {
                    'verifier': self.device_id,
                    'id': self.device_id,
                    'platform': 'web',
                    'device_id': self.device_id,
                }
            
            response = requests.post(url, json=json_data, headers=self.headers, timeout=self.get_timeout())
            response.raise_for_status()
            
            data = response.json()
            self.access_token = data.get('access_token')
            expires_in = data.get('expires_in', 3600)
            self.token_expires_at = time.time() + expires_in - 300  # 5 min buffer
            
            return self.access_token
            
        except Exception as e:
            self.logger.error(f"Error getting Tubi access token: {e}")
            return ""
    
    def get_channels(self) -> List[Dict[str, Any]]:
        """Get Tubi channels"""
        try:
            # Get channel list from API
            url = "https://tubitv.com/live"
            response = requests.get(url, headers=self.headers, timeout=self.get_timeout())
            response.raise_for_status()
            
            html_content = response.text
            
            # Parse the HTML to extract channel data
            import re
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html_content, "html.parser")
            script_tags = soup.find_all("script")
            
            # Find the script with window.__data
            target_script = None
            for script in script_tags:
                if script.string and script.string.strip().startswith("window.__data"):
                    target_script = script.string
                    break
            
            if not target_script:
                self.logger.error("Could not find channel data in Tubi page")
                return []
            
            # Extract JSON data
            start_index = target_script.find("{")
            end_index = target_script.rfind("}") + 1
            json_string = target_script[start_index:end_index]
            
            # Clean up the JSON
            json_string = re.sub(r'\bundefined\b', 'null', json_string)
            
            try:
                data_json = json.loads(json_string)
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse Tubi channel data: {e}")
                return []
            
            # Extract channel IDs
            epg = data_json.get('epg', {})
            content_ids_by_container = epg.get('contentIdsByContainer', {})
            
            skip_slugs = ['favorite_linear_channels', 'recommended_linear_channels', 
                         'featured_channels', 'recently_added_channels']
            
            channel_list = []
            for key in content_ids_by_container.keys():
                for item in content_ids_by_container[key]:
                    if item['container_slug'] not in skip_slugs:
                        channel_list.extend(item["contents"])
            
            channel_list = list(set(channel_list))
            
            if not channel_list:
                self.logger.warning("No channels found in Tubi data")
                return []
            
            # Get detailed channel information
            processed_channels = []
            
            # Process channels in batches
            batch_size = 150
            for i in range(0, len(channel_list), batch_size):
                batch = channel_list[i:i + batch_size]
                batch_channels = self._get_channel_details(batch)
                processed_channels.extend(batch_channels)
            
            self.logger.info(f"Successfully processed {len(processed_channels)} Tubi channels")
            return processed_channels
            
        except Exception as e:
            self.logger.error(f"Error fetching Tubi channels: {e}")
            return []
    
    def _get_channel_details(self, channel_ids: List[str]) -> List[Dict[str, Any]]:
        """Get detailed information for a batch of channels"""
        try:
            params = {"content_id": ','.join(map(str, channel_ids))}
            url = 'https://tubitv.com/oz/epg/programming'
            
            response = requests.get(url, params=params, headers=self.headers, timeout=self.get_timeout())
            response.raise_for_status()
            
            data = response.json()
            epg_data = data.get('rows', [])
            
            processed_channels = []
            
            for channel_data in epg_data:
                try:
                    content_id = str(channel_data.get('content_id', ''))
                    title = channel_data.get('title', '')
                    
                    if not content_id or not title:
                        continue
                    
                    # Check if channel has video resources
                    video_resources = channel_data.get('video_resources', [])
                    if not video_resources or not video_resources[0].get('manifest', {}).get('url'):
                        self.logger.warning(f"No video data for {title}")
                        continue
                    
                    # Build stream URL
                    manifest_url = video_resources[0]['manifest']['url']
                    from urllib.parse import unquote
                    stream_url = f"{unquote(manifest_url)}&content_id={content_id}"
                    
                    # Get channel info
                    images = channel_data.get('images', {})
                    logo = images.get('thumbnail', [''])[0] if isinstance(images.get('thumbnail'), list) else images.get('thumbnail', '')
                    
                    channel = {
                        'id': content_id,
                        'name': title,
                        'stream_url': stream_url,
                        'logo': logo,
                        'group': 'Tubi',
                        'description': f"Tubi channel: {title}",
                        'language': 'en'
                    }
                    
                    if self.validate_channel(channel):
                        processed_channels.append(self.normalize_channel(channel))
                        
                except Exception as e:
                    self.logger.warning(f"Error processing Tubi channel: {e}")
                    continue
            
            return processed_channels
            
        except Exception as e:
            self.logger.error(f"Error getting Tubi channel details: {e}")
            return []
    
    def get_epg_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get EPG data for Tubi channels"""
        try:
            # For this unified version, we'll return empty EPG data
            # In a full implementation, this would fetch EPG data from Tubi's EPG endpoints
            self.logger.info("EPG data fetching not implemented for Tubi provider in this version")
            return {}
            
        except Exception as e:
            self.logger.error(f"Error fetching Tubi EPG data: {e}")
            return {}