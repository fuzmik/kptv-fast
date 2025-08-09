"""
Xumo Provider Implementation
"""

import requests
import json
import os
import uuid
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from .base_provider import BaseProvider

class XumoProvider(BaseProvider):
    """Provider for Xumo TV channels"""
    
    def __init__(self):
        super().__init__("xumo")
        
        # Configuration
        self.valencia_api_endpoint = "https://valencia-app-mds.xumo.com/v2"
        self.android_tv_endpoint = "https://android-tv-mds.xumo.com/v2"
        self.geo_id = "us"
        self.primary_list_id = "10006"
        
        # Headers
        self.web_headers = {
            'User-Agent': self.get_user_agent(),
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Origin': 'https://play.xumo.com',
            'Referer': 'https://play.xumo.com/',
        }
        
        self.android_tv_headers = {
            'User-Agent': 'okhttp/4.9.3',
        }
        
    def _fetch_data(self, url: str, headers: dict = None, params: dict = None, retries: int = 2) -> dict:
        """Fetch data from URL with retries"""
        if headers is None:
            headers = self.web_headers
            
        for attempt in range(retries + 1):
            try:
                response = requests.get(
                    url, 
                    headers=headers, 
                    params=params, 
                    timeout=self.get_timeout()
                )
                response.raise_for_status()
                
                if response.content:
                    return response.json()
                else:
                    self.logger.warning(f"Empty response from {url}")
                    return {}
                    
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt == retries:
                    self.logger.error(f"All attempts failed for {url}")
                    return {}
                time.sleep(2 ** attempt)
                
        return {}
    
    def _process_stream_uri(self, uri: str) -> str:
        """Process stream URI by replacing placeholders"""
        if not uri:
            return ""
            
        try:
            # Replace placeholder values
            replacements = {
                '[PLATFORM]': "web",
                '[APP_VERSION]': "1.0.0",
                '[timestamp]': str(int(time.time() * 1000)),
                '[app_bundle]': "web.xumo.com",
                '[device_make]': "UnifiedAggregator",
                '[device_model]': "WebClient",
                '[content_language]': "en",
                '[IS_LAT]': "0",
                '[IFA]': str(uuid.uuid4()),
                '[SESSION_ID]': str(uuid.uuid4()),
                '[DEVICE_ID]': str(uuid.uuid4().hex)
            }
            
            for placeholder, value in replacements.items():
                uri = uri.replace(placeholder, value)
                
            # Remove any remaining placeholders
            import re
            uri = re.sub(r'\[([^]]+)\]', '', uri)
            
            return uri
            
        except Exception as e:
            self.logger.error(f"Error processing stream URI: {e}")
            return uri
    
    def get_channels(self) -> List[Dict[str, Any]]:
        """Get Xumo channels"""
        try:
            # Get channel list from Valencia endpoint
            url = f"{self.valencia_api_endpoint}/proxy/channels/list/{self.primary_list_id}.json"
            params = {'geoId': self.geo_id}
            
            data = self._fetch_data(url, self.web_headers, params)
            if not data:
                self.logger.error("Failed to fetch channel list")
                return []
            
            # Extract channels
            channel_items = []
            if 'channel' in data and 'item' in data['channel']:
                channel_items = data['channel']['item']
            elif 'items' in data:
                channel_items = data['items']
            else:
                self.logger.error("Could not find channel list in response")
                return []
            
            processed_channels = []
            
            for item in channel_items:
                try:
                    # Skip DRM and non-live channels
                    callsign = item.get('callsign', '')
                    properties = item.get('properties', {})
                    is_live = properties.get('is_live') == "true"
                    is_drm = callsign.endswith("-DRM") or callsign.endswith("DRM-CMS")
                    
                    if is_drm or not is_live:
                        continue
                    
                    channel_id = item.get('guid', {}).get('value')
                    title = item.get('title')
                    number_str = item.get('number')
                    logo_url = item.get('images', {}).get('logo') or item.get('logo')
                    
                    if not channel_id or not title:
                        continue
                    
                    # Process logo URL
                    if logo_url:
                        if logo_url.startswith('//'):
                            logo_url = 'https:' + logo_url
                        elif logo_url.startswith('/'):
                            logo_url = 'https://image.xumo.com' + logo_url
                    else:
                        logo_url = f"https://image.xumo.com/v1/channels/channel/{channel_id}/168x168.png?type=color_onBlack"
                    
                    # Get genre
                    genre_list = item.get('genre')
                    genre = 'General'
                    if isinstance(genre_list, list) and genre_list:
                        if isinstance(genre_list[0], dict):
                            genre = genre_list[0].get('value', 'General')
                    elif isinstance(genre_list, str):
                        genre = genre_list
                    
                    # Get stream URL via asset lookup
                    stream_url = self._get_stream_url(channel_id)
                    if not stream_url:
                        self.logger.warning(f"No stream URL found for channel {channel_id}")
                        continue
                    
                    channel = {
                        'id': str(channel_id),
                        'name': title,
                        'stream_url': stream_url,
                        'logo': logo_url,
                        'group': genre,
                        'number': int(number_str) if number_str else None,
                        'description': f"Xumo channel: {title}",
                        'language': 'en'
                    }
                    
                    if self.validate_channel(channel):
                        processed_channels.append(self.normalize_channel(channel))
                        
                except Exception as e:
                    self.logger.warning(f"Error processing channel item: {e}")
                    continue
            
            self.logger.info(f"Successfully processed {len(processed_channels)} Xumo channels")
            return processed_channels
            
        except Exception as e:
            self.logger.error(f"Error fetching Xumo channels: {e}")
            return []
    
    def _get_stream_url(self, channel_id: str) -> str:
        """Get stream URL for a channel via asset lookup"""
        try:
            # Get current broadcast
            current_hour = datetime.now(timezone.utc).hour
            broadcast_url = f"{self.android_tv_endpoint}/channels/channel/{channel_id}/broadcast.json"
            params = {'hour': current_hour}
            
            broadcast_data = self._fetch_data(broadcast_url, self.android_tv_headers, params)
            if not broadcast_data or 'assets' not in broadcast_data:
                return ""
            
            # Find current asset
            now_utc = datetime.now(timezone.utc)
            current_asset = None
            
            for asset in broadcast_data['assets']:
                start_time_str = asset.get('start')
                end_time_str = asset.get('end')
                
                if start_time_str and end_time_str:
                    try:
                        start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                        end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
                        
                        if start_time <= now_utc < end_time:
                            current_asset = asset
                            break
                    except:
                        continue
            
            if not current_asset and broadcast_data['assets']:
                current_asset = broadcast_data['assets'][0]
            
            if not current_asset:
                return ""
            
            asset_id = current_asset.get('id')
            if not asset_id:
                return ""
            
            # Get asset details
            asset_url = f"{self.android_tv_endpoint}/assets/asset/{asset_id}.json"
            params = {'f': 'providers'}
            
            asset_data = self._fetch_data(asset_url, self.android_tv_headers, params)
            if not asset_data or 'providers' not in asset_data:
                return ""
            
            # Find stream URI
            for provider in asset_data['providers']:
                if 'sources' in provider:
                    for source in provider['sources']:
                        uri = source.get('uri')
                        if uri and (source.get('type') == 'application/x-mpegURL' or uri.endswith('.m3u8')):
                            return self._process_stream_uri(uri)
            
            return ""
            
        except Exception as e:
            self.logger.error(f"Error getting stream URL for channel {channel_id}: {e}")
            return ""
    
    def get_epg_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get EPG data for Xumo channels"""
        try:
            # For this unified version, we'll return empty EPG data
            # In a full implementation, this would fetch EPG data from Xumo's EPG endpoints
            self.logger.info("EPG data fetching not implemented for Xumo provider in this version")
            return {}
            
        except Exception as e:
            self.logger.error(f"Error fetching Xumo EPG data: {e}")
            return {}