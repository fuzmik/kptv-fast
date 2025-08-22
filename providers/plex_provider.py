"""
Plex Provider Implementation
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
        try:
            token = self._get_access_token()
            if not token:
                self.logger.error("Could not get Plex access token for EPG")
                return {}
            
            # Get current channels
            channels = self.get_channels()
            if not channels:
                return {}
            
            epg_data = {}
            
            # Try different EPG endpoints
            endpoints_to_try = [
                'https://epg.provider.plex.tv/v2/grid',
                'https://epg.provider.plex.tv/guide',
                'https://epg.provider.plex.tv/lineups/plex/grid'
            ]
            
            headers = self.headers.copy()
            params = self.params.copy()
            params['X-Plex-Token'] = token
            
            if self.region in self.x_forward:
                forwarded_ip = self.x_forward[self.region]
                if forwarded_ip:
                    headers["X-Forwarded-For"] = forwarded_ip
            
            # Get current time in different formats
            from datetime import datetime, timezone, timedelta
            
            now = datetime.now(timezone.utc)
            
            # Try different time formats
            time_formats = [
                {
                    'start': now.strftime('%Y-%m-%dT%H:00:00Z'),
                    'end': (now + timedelta(hours=24)).strftime('%Y-%m-%dT%H:00:00Z')
                },
                {
                    'start': str(int(now.timestamp())),
                    'end': str(int((now + timedelta(hours=24)).timestamp()))
                },
                {
                    'startTime': str(int(now.timestamp())),
                    'endTime': str(int((now + timedelta(hours=24)).timestamp()))
                }
            ]
            
            success = False
            
            for endpoint in endpoints_to_try:
                if success:
                    break
                    
                for time_format in time_formats:
                    try:
                        test_params = params.copy()
                        test_params.update(time_format)
                        
                        self.logger.debug(f"Trying Plex EPG endpoint: {endpoint} with time format: {time_format}")
                        
                        response = self.make_request('GET', endpoint, params=test_params, headers=headers)
                        
                        if response.status_code == 200:
                            data = response.json()
                            
                            # Try to parse response
                            programs = []
                            
                            # Handle different response structures
                            if 'MediaContainer' in data:
                                programs = data.get('MediaContainer', {}).get('Metadata', [])
                            elif 'programs' in data:
                                programs = data.get('programs', [])
                            elif 'data' in data:
                                programs = data.get('data', [])
                            elif isinstance(data, list):
                                programs = data
                            
                            if programs:
                                self.logger.info(f"Successfully got Plex EPG data from {endpoint}: {len(programs)} programs")
                                
                                # Process programs
                                for program in programs:
                                    try:
                                        channel_id = program.get('channelId') or program.get('channel_id') or program.get('channelID')
                                        if not channel_id:
                                            continue
                                        
                                        our_channel_id = f"plex-{channel_id}"
                                        
                                        # Handle different time field names
                                        start_time = (program.get('startTime') or 
                                                    program.get('start_time') or 
                                                    program.get('start') or 
                                                    program.get('airDate'))
                                        
                                        end_time = (program.get('endTime') or 
                                                program.get('end_time') or 
                                                program.get('end') or 
                                                program.get('duration'))
                                        
                                        title = program.get('title', '')
                                        description = (program.get('summary') or 
                                                    program.get('description') or 
                                                    program.get('plot', ''))
                                        
                                        if start_time and title:
                                            # Convert timestamps
                                            if isinstance(start_time, str) and start_time.isdigit():
                                                start_dt = datetime.fromtimestamp(int(start_time), timezone.utc)
                                            elif isinstance(start_time, (int, float)):
                                                start_dt = datetime.fromtimestamp(start_time, timezone.utc)
                                            else:
                                                # Try parsing ISO format
                                                start_dt = datetime.fromisoformat(str(start_time).replace('Z', '+00:00'))
                                            
                                            # Calculate end time if duration provided
                                            if end_time:
                                                if isinstance(end_time, str) and end_time.isdigit():
                                                    end_dt = datetime.fromtimestamp(int(end_time), timezone.utc)
                                                elif isinstance(end_time, (int, float)):
                                                    if end_time < 86400:  # Looks like duration in seconds
                                                        end_dt = start_dt + timedelta(seconds=end_time)
                                                    else:  # Looks like timestamp
                                                        end_dt = datetime.fromtimestamp(end_time, timezone.utc)
                                                else:
                                                    end_dt = datetime.fromisoformat(str(end_time).replace('Z', '+00:00'))
                                            else:
                                                # Default 30 minute duration
                                                end_dt = start_dt + timedelta(minutes=30)
                                            
                                            programme = {
                                                'title': title,
                                                'description': description,
                                                'start': start_dt.strftime('%Y%m%d%H%M%S %z'),
                                                'stop': end_dt.strftime('%Y%m%d%H%M%S %z'),
                                                'category': program.get('genre', ''),
                                            }
                                            
                                            if self.validate_programme(programme):
                                                if our_channel_id not in epg_data:
                                                    epg_data[our_channel_id] = []
                                                epg_data[our_channel_id].append(self.normalize_programme(programme))
                                                
                                    except Exception as e:
                                        self.logger.debug(f"Error processing Plex programme: {e}")
                                        continue
                                
                                success = True
                                break
                                
                        else:
                            self.logger.debug(f"Plex EPG endpoint {endpoint} returned {response.status_code}")
                            
                    except Exception as e:
                        self.logger.debug(f"Error trying Plex EPG endpoint {endpoint}: {e}")
                        continue
            
            if epg_data:
                self.logger.info(f"Retrieved EPG data for {len(epg_data)} Plex channels")
            else:
                self.logger.warning("No EPG data retrieved from any Plex endpoint")
            
            # If no EPG data from native method, try fallback
            if not epg_data:
                try:
                    from utils.epg_fallback import EPGFallbackManager
                    fallback_manager = EPGFallbackManager()
                    epg_data = fallback_manager.get_fallback_epg('plex', channels)
                    if epg_data:
                        self.logger.info(f"Using fallback EPG for plex: {len(epg_data)} channels")
                except Exception as e:
                    self.logger.debug(f"Fallback EPG failed for plex: {e}")
            
            return epg_data
            
        except Exception as e:
            self.logger.error(f"Error fetching Plex EPG data: {e}")
            
            # Try fallback on error
            try:
                from utils.epg_fallback import EPGFallbackManager
                fallback_manager = EPGFallbackManager()
                channels = self.get_channels()
                epg_data = fallback_manager.get_fallback_epg('plex', channels)
                if epg_data:
                    self.logger.info(f"Using fallback EPG for plex: {len(epg_data)} channels")
                return epg_data
            except Exception as e:
                self.logger.debug(f"Fallback EPG failed for plex: {e}")
                return {}