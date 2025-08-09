"""
Plex and Samsung Provider Implementations
"""

import requests
import json
import uuid
import gzip
import os
import time
import string
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any
from io import BytesIO
from .base_provider import BaseProvider

class PlexProvider(BaseProvider):
    """Provider for Plex channels"""
    
    def __init__(self):
        super().__init__("plex")
        
        self.device_id = self._generate_device_id()
        self.access_token = None
        self.token_expires_at = 0
        
        # Get region from environment or default to local
        self.region = os.getenv('PLEX_REGION', 'local')
        
        self.headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en',
            'Connection': 'keep-alive',
            'Origin': 'https://app.plex.tv',
            'Referer': 'https://app.plex.tv/',
            'User-Agent': self.get_user_agent(),
            'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
        }
        
        self.params = {
            'X-Plex-Product': 'Plex Web',
            'X-Plex-Version': '4.145.0',
            'X-Plex-Platform': 'Chrome',
            'X-Plex-Platform-Version': '132.0',
            'X-Plex-Features': 'external-media,indirect-media,hub-style-list',
            'X-Plex-Model': 'standalone',
            'X-Plex-Device': 'OSX',
            'X-Plex-Device-Screen-Resolution': '1758x627,1920x1080',
            'X-Plex-Provider-Version': '7.2',
            'X-Plex-Text-Format': 'plain',
            'X-Plex-Drm': 'widevine',
            'X-Plex-Language': 'en',
            'X-Plex-Client-Identifier': self.device_id,
        }
        
        # Regional IPs for geo-spoofing
        self.x_forward = {
            "local": "",
            "clt": "108.82.206.181",
            "sea": "159.148.218.183", 
            "dfw": "76.203.9.148",
            "nyc": "85.254.181.50",
            "la": "76.81.9.69",
        }
    
    def _generate_device_id(self) -> str:
        """Generate a device ID for Plex"""
        length = 24
        characters = string.ascii_lowercase + string.digits
        return ''.join(random.choice(characters) for _ in range(length))
    
    def _get_access_token(self) -> str:
        """Get Plex access token"""
        if self.access_token and time.time() < self.token_expires_at:
            return self.access_token
        
        try:
            url = 'https://clients.plex.tv/api/v2/users/anonymous'
            headers = self.headers.copy()
            
            if self.region in self.x_forward:
                forwarded_ip = self.x_forward[self.region]
                if forwarded_ip:
                    headers["X-Forwarded-For"] = forwarded_ip
            
            response = requests.post(url, params=self.params, headers=headers, timeout=self.get_timeout())
            response.raise_for_status()
            
            data = response.json()
            self.access_token = data.get('authToken', '')
            
            if not self.access_token:
                self.logger.error("No auth token received from Plex")
                return ""
            
            # Set expiry for 6 hours from now
            self.token_expires_at = time.time() + (6 * 3600)
            self.logger.info(f"Successfully authenticated with Plex for region: {self.region}")
            
            return self.access_token
            
        except Exception as e:
            self.logger.error(f"Error getting Plex access token: {e}")
            return ""
    
    def get_channels(self) -> List[Dict[str, Any]]:
        """Get Plex channels"""
        try:
            token = self._get_access_token()
            if not token:
                self.logger.error("Could not get Plex access token")
                return []
            
            # Get genre list first
            url = 'https://epg.provider.plex.tv/'
            headers = self.headers.copy()
            params = self.params.copy()
            params['X-Plex-Token'] = token
            
            if self.region in self.x_forward:
                forwarded_ip = self.x_forward[self.region]
                if forwarded_ip:
                    headers["X-Forwarded-For"] = forwarded_ip
            
            response = requests.get(url, params=params, headers=headers, timeout=self.get_timeout())
            response.raise_for_status()
            
            data = response.json()
            genres = {}
            
            # Extract genres from MediaProvider
            features = data.get('MediaProvider', {}).get('Feature', [])
            for feature in features:
                if 'GridChannelFilter' in feature:
                    for genre in feature.get('GridChannelFilter', []):
                        genre_id = genre.get('identifier')
                        genre_name = genre.get('title')
                        if genre_id and genre_name:
                            genres[genre_id] = genre_name
                    break
            
            if not genres:
                self.logger.warning("No genres found in Plex data")
                return []
            
            # Get channels for each genre
            processed_channels = []
            
            for genre_id, genre_name in genres.items():
                try:
                    channels_url = f'https://epg.provider.plex.tv/lineups/plex/channels?genre={genre_id}'
                    
                    response = requests.get(channels_url, params=params, headers=headers, timeout=self.get_timeout())
                    if response.status_code != 200:
                        self.logger.warning(f"Failed to get channels for genre {genre_name}: {response.status_code}")
                        continue
                    
                    channel_data = response.json()
                    channels = channel_data.get("MediaContainer", {}).get("Channel", [])
                    
                    if not channels:
                        continue
                    
                    for channel in channels:
                        try:
                            channel_id = channel.get('id')
                            name = channel.get('title')
                            slug = channel.get('slug')
                            logo = channel.get('thumb')
                            call_sign = channel.get('callSign')
                            
                            if not channel_id or not name:
                                continue
                            
                            # Check for DRM - skip DRM channels
                            has_drm = any(media.get("drm", False) for media in channel.get("Media", []))
                            if has_drm:
                                self.logger.debug(f"Skipping DRM channel: {name}")
                                continue
                            
                            # Get stream key from Media/Part
                            key_values = []
                            for media in channel.get("Media", []):
                                for part in media.get("Part", []):
                                    if part.get("key"):
                                        key_values.append(part["key"])
                            
                            if not key_values:
                                self.logger.debug(f"No stream key found for channel: {name}")
                                continue
                            
                            # Build stream URL
                            stream_url = f"https://epg.provider.plex.tv{key_values[0]}?X-Plex-Token={token}"
                            
                            channel_info = {
                                'id': f"plex-{channel_id}",
                                'name': name,
                                'stream_url': stream_url,
                                'logo': logo or '',
                                'group': genre_name,
                                'description': f"Plex channel: {name}",
                                'language': 'en'
                            }
                            
                            if self.validate_channel(channel_info):
                                processed_channels.append(self.normalize_channel(channel_info))
                                
                        except Exception as e:
                            self.logger.warning(f"Error processing Plex channel: {e}")
                            continue
                            
                except Exception as e:
                    self.logger.warning(f"Error fetching channels for genre {genre_name}: {e}")
                    continue
            
            self.logger.info(f"Successfully processed {len(processed_channels)} Plex channels from region: {self.region}")
            return processed_channels
            
        except Exception as e:
            self.logger.error(f"Error fetching Plex channels: {e}")
            return []
    
    def get_epg_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get EPG data for Plex channels"""
        self.logger.info("EPG data fetching not implemented for Plex provider in this version")
        return {}

class SamsungProvider(BaseProvider):
    """Provider for Samsung TV Plus channels"""
    
    def __init__(self):
        super().__init__("samsung")
        
        # Get region from environment or default to US
        self.region = os.getenv('SAMSUNG_REGION', 'us')
        
        self.app_url = 'https://i.mjh.nz/SamsungTVPlus/.channels.json.gz'
        self.playback_url_template = 'https://jmp2.uk/sam-{id}.m3u8'
        
        self.headers = {
            'User-Agent': self.get_user_agent(),
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    
    def _get_app_data(self) -> dict:
        """Get Samsung TV Plus app data"""
        try:
            response = requests.get(self.app_url, headers=self.headers, timeout=self.get_timeout())
            response.raise_for_status()
            
            # Decompress and parse JSON
            json_text = gzip.GzipFile(fileobj=BytesIO(response.content)).read()
            data = json.loads(json_text)
            
            return data.get('regions', {})
            
        except Exception as e:
            self.logger.error(f"Error getting Samsung app data: {e}")
            return {}
    
    def get_channels(self) -> List[Dict[str, Any]]:
        """Get Samsung TV Plus channels"""
        try:
            all_regions = self._get_app_data()
            
            if not all_regions:
                self.logger.error("Could not get Samsung channel data")
                return []
            
            # Use specified region or all regions
            if self.region == 'all':
                regions_to_process = all_regions.values()
                self.logger.info("Processing Samsung channels from all regions")
            elif self.region in all_regions:
                regions_to_process = [all_regions[self.region]]
                self.logger.info(f"Processing Samsung channels from region: {self.region}")
            else:
                self.logger.warning(f"Region {self.region} not found in Samsung data, using US")
                regions_to_process = [all_regions.get('us', {})]
            
            processed_channels = []
            
            for region_data in regions_to_process:
                channels = region_data.get('channels', {})
                region_name = region_data.get('name', 'Unknown')
                
                for channel_id, channel_data in channels.items():
                    try:
                        name = channel_data.get('name', '')
                        logo = channel_data.get('logo', '')
                        group = channel_data.get('group', 'General')
                        chno = channel_data.get('chno')
                        
                        if not name:
                            continue
                        
                        # Skip channels that require a license (DRM)
                        if channel_data.get('license_url'):
                            self.logger.debug(f"Skipping DRM channel: {name}")
                            continue
                        
                        # Build stream URL
                        stream_url = self.playback_url_template.format(id=channel_id)
                        
                        channel = {
                            'id': f"samsung-{channel_id}",
                            'name': name,
                            'stream_url': stream_url,
                            'logo': logo,
                            'group': group,
                            'number': int(chno) if chno else None,
                            'description': f"Samsung TV Plus channel: {name}",
                            'language': 'en'
                        }
                        
                        if self.validate_channel(channel):
                            processed_channels.append(self.normalize_channel(channel))
                            
                    except Exception as e:
                        self.logger.warning(f"Error processing Samsung channel: {e}")
                        continue
            
            self.logger.info(f"Successfully processed {len(processed_channels)} Samsung TV Plus channels")
            return processed_channels
            
        except Exception as e:
            self.logger.error(f"Error fetching Samsung TV Plus channels: {e}")
            return []
    
    def get_epg_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get EPG data for Samsung TV Plus channels"""
        try:
            # Samsung provides EPG data via a separate endpoint
            epg_url = f'https://i.mjh.nz/SamsungTVPlus/{self.region}.xml.gz'
            
            response = requests.get(epg_url, headers=self.headers, timeout=self.get_timeout())
            response.raise_for_status()
            
            # Decompress EPG data
            epg_xml = gzip.GzipFile(fileobj=BytesIO(response.content)).read().decode('utf-8')
            
            # Parse EPG XML to extract program data
            import xml.etree.ElementTree as ET
            
            root = ET.fromstring(epg_xml)
            epg_data = {}
            
            # Extract programme elements
            for programme in root.findall('programme'):
                channel_id = programme.get('channel', '')
                if not channel_id:
                    continue
                
                # Convert Samsung channel ID to our format
                formatted_channel_id = f"samsung-{channel_id}"
                
                if formatted_channel_id not in epg_data:
                    epg_data[formatted_channel_id] = []
                
                # Extract programme info
                title_elem = programme.find('title')
                desc_elem = programme.find('desc')
                
                programme_info = {
                    'title': title_elem.text if title_elem is not None else '',
                    'description': desc_elem.text if desc_elem is not None else '',
                    'start': programme.get('start', ''),
                    'stop': programme.get('stop', ''),
                }
                
                if self.validate_programme(programme_info):
                    epg_data[formatted_channel_id].append(self.normalize_programme(programme_info))
            
            self.logger.info(f"Retrieved EPG data for {len(epg_data)} Samsung channels")
            return epg_data
            
        except Exception as e:
            self.logger.error(f"Error fetching Samsung EPG data: {e}")
            return {}