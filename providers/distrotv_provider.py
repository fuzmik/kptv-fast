"""
DistroTV Provider Implementation
Scrapes DistroTV website for live channels and EPG data
"""

import requests
import json
import re
import os
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from urllib.parse import urljoin, urlparse
from .base_provider import BaseProvider

try:
    from bs4 import BeautifulSoup # type: ignore
    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    BEAUTIFULSOUP_AVAILABLE = False

class DistroTVProvider(BaseProvider):
    """Provider for DistroTV channels"""
    
    def __init__(self):
        super().__init__("distrotv")
        
        self.base_url = "https://www.distro.tv"
        self.live_url = f"{self.base_url}/live/"
        
        # User agent for web scraping
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }
        
        # Channel cache
        self.channels_cache = []
        self.cache_expiry = 0
        self.cache_duration = 1800  # 30 minutes
    
    def _get_page_content(self, url: str) -> str:
        """Get page content with error handling"""
        try:
            response = self.make_request('GET', url, headers=self.headers, timeout=(10, 30))
            response.raise_for_status()
            return response.text
        except Exception as e:
            self.logger.warning(f"Error fetching page {url}: {e}")
            return ""
    
    def _scrape_with_beautifulsoup(self, html_content: str) -> List[Dict[str, Any]]:
        """Scrape channels using BeautifulSoup"""
        if not BEAUTIFULSOUP_AVAILABLE:
            return []
        
        channels = []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Look for channel containers
            channel_selectors = [
                'a[href*="/live/"]',
                '.channel-item',
                '.live-channel',
                '[data-channel]',
                '.channel-card',
                '.channel-link'
            ]
            
            for selector in channel_selectors:
                channel_elements = soup.select(selector)
                if channel_elements:
                    self.logger.debug(f"Found {len(channel_elements)} elements with selector: {selector}")
                    
                    for element in channel_elements:
                        channel = self._extract_channel_from_element(element)
                        if channel:
                            channels.append(channel)
                    
                    if channels:
                        break
            
            # Also look for embedded JSON data
            if not channels:
                script_tags = soup.find_all('script')
                for script in script_tags:
                    if script.string:
                        json_channels = self._extract_json_from_script(script.string)
                        if json_channels:
                            channels.extend(json_channels)
            
        except Exception as e:
            self.logger.error(f"Error scraping with BeautifulSoup: {e}")
        
        return channels
    
    def _extract_channel_from_element(self, element) -> Dict[str, Any]:
        """Extract channel data from HTML element"""
        try:
            # Get channel URL/slug
            href = element.get('href', '')
            if '/live/' in href:
                slug = href.split('/live/')[-1].rstrip('/')
            else:
                slug = element.get('data-channel', '') or element.get('data-slug', '')
            
            if not slug:
                return None
            
            # Get channel name
            name = ''
            name_selectors = ['title', 'data-title', 'alt']
            for attr in name_selectors:
                name = element.get(attr, '')
                if name:
                    break
            
            if not name:
                # Try to get text content
                name = element.get_text(strip=True)
                # Clean up common patterns
                name = re.sub(r'LIVE\s*', '', name, flags=re.IGNORECASE)
                name = re.sub(r'\s+', ' ', name).strip()
            
            if not name or len(name) < 2:
                return None
            
            # Get logo
            logo = ''
            img_tag = element.find('img')
            if img_tag:
                logo = img_tag.get('src', '') or img_tag.get('data-src', '')
                if logo and not logo.startswith('http'):
                    logo = urljoin(self.base_url, logo)
            
            # Create stream URL
            stream_url = self._construct_stream_url(slug)
            
            return {
                'id': f"distrotv-{slug}",
                'name': name,
                'stream_url': stream_url,
                'logo': logo,
                'group': 'DistroTV',
                'description': f"DistroTV channel: {name}",
                'language': 'en'
            }
            
        except Exception as e:
            self.logger.debug(f"Error extracting channel from element: {e}")
            return None
    
    def _extract_json_from_script(self, script_content: str) -> List[Dict[str, Any]]:
        """Extract channel data from JavaScript"""
        channels = []
        
        try:
            # Look for various patterns
            patterns = [
                r'channels\s*[:=]\s*(\[.+?\])',
                r'"channels"\s*:\s*(\[.+?\])',
                r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                r'window\.__APP_DATA__\s*=\s*({.+?});',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, script_content, re.DOTALL)
                for match in matches:
                    try:
                        data = json.loads(match)
                        extracted = self._parse_json_channels(data)
                        if extracted:
                            channels.extend(extracted)
                            self.logger.debug(f"Extracted {len(extracted)} channels from JSON")
                    except (json.JSONDecodeError, TypeError):
                        continue
            
        except Exception as e:
            self.logger.debug(f"Error extracting JSON from script: {e}")
        
        return channels
    
    def _parse_json_channels(self, data: Any) -> List[Dict[str, Any]]:
        """Parse channel data from JSON"""
        channels = []
        
        try:
            if isinstance(data, list):
                # Direct list of channels
                for item in data:
                    if isinstance(item, dict):
                        channel = self._format_json_channel(item)
                        if channel:
                            channels.append(channel)
            
            elif isinstance(data, dict):
                # Look for channels in nested structure
                channels_data = None
                if 'channels' in data:
                    channels_data = data['channels']
                elif 'live' in data and isinstance(data['live'], dict):
                    channels_data = data['live'].get('channels', [])
                elif 'data' in data and isinstance(data['data'], dict):
                    channels_data = data['data'].get('channels', [])
                
                if channels_data and isinstance(channels_data, list):
                    for item in channels_data:
                        if isinstance(item, dict):
                            channel = self._format_json_channel(item)
                            if channel:
                                channels.append(channel)
        
        except Exception as e:
            self.logger.debug(f"Error parsing JSON channels: {e}")
        
        return channels
    
    def _format_json_channel(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format channel data from JSON"""
        try:
            channel_id = data.get('id') or data.get('slug') or data.get('name', '').lower().replace(' ', '-')
            name = data.get('name') or data.get('title', '')
            
            if not channel_id or not name:
                return None
            
            logo = data.get('logo', '') or data.get('image', '') or data.get('poster', '')
            if logo and not logo.startswith('http'):
                logo = urljoin(self.base_url, logo)
            
            group = data.get('category', '') or data.get('genre', '') or 'DistroTV'
            
            # Get stream URL
            stream_url = data.get('stream_url') or data.get('url') or self._construct_stream_url(channel_id)
            
            return {
                'id': f"distrotv-{channel_id}",
                'name': name,
                'stream_url': stream_url,
                'logo': logo,
                'group': group,
                'description': f"DistroTV channel: {name}",
                'language': 'en'
            }
            
        except Exception as e:
            self.logger.debug(f"Error formatting JSON channel: {e}")
            return None
    
    def _construct_stream_url(self, slug: str) -> str:
        """Construct stream URL from channel slug"""
        # Try different DistroTV stream URL patterns
        patterns = [
            f"https://dai.google.com/linear/hls/event/{slug}/master.m3u8",
            f"https://content.uplynk.com/channel/{slug}.m3u8",
            f"https://stream.ads.ottera.tv/playlist.m3u8?network_id={slug}",
        ]
        
        # Return first pattern for now
        return patterns[0]
    
    def _scrape_with_regex(self, html_content: str) -> List[Dict[str, Any]]:
        """Fallback scraping using regex"""
        channels = []
        
        try:
            # Look for channel links
            link_patterns = [
                r'<a[^>]*href=["\']([^"\']*\/live\/[^"\']+)["\'][^>]*>.*?([^<]+)',
                r'href=["\']\/live\/([^"\']+)["\'][^>]*.*?title=["\']([^"\']+)["\']',
                r'data-channel=["\']([^"\']+)["\'][^>]*.*?>([^<]+)',
            ]
            
            for pattern in link_patterns:
                matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
                for match in matches:
                    try:
                        if len(match) == 2:
                            slug, name = match
                            if '/live/' in slug:
                                slug = slug.split('/live/')[-1].rstrip('/')
                            
                            name = re.sub(r'<[^>]+>', '', name).strip()
                            name = re.sub(r'\s+', ' ', name)
                            
                            if slug and name and len(name) > 2:
                                channel = {
                                    'id': f"distrotv-{slug}",
                                    'name': name,
                                    'stream_url': self._construct_stream_url(slug),
                                    'logo': '',
                                    'group': 'DistroTV',
                                    'description': f"DistroTV channel: {name}",
                                    'language': 'en'
                                }
                                channels.append(channel)
                    except Exception as e:
                        self.logger.debug(f"Error processing regex match: {e}")
                        continue
                
                if channels:
                    break
            
        except Exception as e:
            self.logger.error(f"Error scraping with regex: {e}")
        
        return channels
        
    def get_epg_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get EPG data for DistroTV channels"""
        try:
            channels = self.get_channels()
            if not channels:
                return {}
            
            # Use fallback EPG
            self.logger.info("Using fallback EPG for DistroTV")
            
            try:
                from utils.epg_fallback import EPGFallbackManager
                fallback_manager = EPGFallbackManager()
                epg_data = fallback_manager.get_fallback_epg('distrotv', channels)
                if epg_data:
                    self.logger.info(f"Retrieved fallback EPG for {len(epg_data)} DistroTV channels")
                return epg_data
            except Exception as e:
                self.logger.error(f"Fallback EPG failed for DistroTV: {e}")
                return {}
        
        except Exception as e:
            self.logger.error(f"Error fetching DistroTV EPG data: {e}")
            return {}
        
    def _get_external_m3u_fallback(self) -> List[Dict[str, Any]]:
        """Get channels from external M3U as absolute last resort"""
        try:
            m3u_url = "https://www.apsattv.com/distro.m3u"
            
            self.logger.info("Using external M3U as last resort fallback")
            response = self.make_request('GET', m3u_url, timeout=(15, 45))
            response.raise_for_status()
            
            m3u_content = response.text
            channels = self._parse_m3u_content(m3u_content)
            
            if channels:
                self.logger.info(f"Parsed {len(channels)} channels from external M3U fallback")
            
            return channels
            
        except Exception as e:
            self.logger.warning(f"External M3U fallback failed: {e}")
            return []

    def _parse_m3u_content(self, content: str) -> List[Dict[str, Any]]:
        """Parse M3U playlist content"""
        channels = []
        lines = content.strip().split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if line.startswith('#EXTINF:'):
                try:
                    # Get the next non-empty line as the URL
                    url_line = ""
                    j = i + 1
                    while j < len(lines):
                        potential_url = lines[j].strip()
                        if potential_url and not potential_url.startswith('#'):
                            url_line = potential_url
                            break
                        j += 1
                    
                    if not url_line:
                        i += 1
                        continue
                    
                    # Parse EXTINF line
                    extinf_content = line[8:]  # Remove '#EXTINF:'
                    
                    channel_name = ""
                    tvg_id = ""
                    tvg_logo = ""
                    group_title = ""
                    
                    if ',' in extinf_content:
                        attr_part, name_part = extinf_content.split(',', 1)
                        channel_name = name_part.strip()
                        
                        # Parse attributes
                        import re
                        tvg_id_match = re.search(r'tvg-id="([^"]*)"', attr_part)
                        tvg_logo_match = re.search(r'tvg-logo="([^"]*)"', attr_part)
                        group_match = re.search(r'group-title="([^"]*)"', attr_part)
                        
                        if tvg_id_match:
                            tvg_id = tvg_id_match.group(1)
                        if tvg_logo_match:
                            tvg_logo = tvg_logo_match.group(1)
                        if group_match:
                            group_title = group_match.group(1)
                    
                    if channel_name and url_line:
                        channel_id = tvg_id if tvg_id else channel_name.lower().replace(' ', '-').replace('&', 'and')
                        channel = {
                            'id': f"distrotv-{channel_id}",
                            'name': channel_name,
                            'stream_url': url_line,
                            'logo': tvg_logo,
                            'group': group_title or 'DistroTV',
                            'description': f"DistroTV channel: {channel_name}",
                            'language': 'en'
                        }
                        channels.append(channel)
                    
                    i = j + 1
                    
                except Exception as e:
                    self.logger.debug(f"Error parsing M3U line: {e}")
                    i += 1
            else:
                i += 1
        
        return channels

    def get_channels(self) -> List[Dict[str, Any]]:
        """Get DistroTV channels via scraping with external M3U fallback"""
        try:
            # Check cache first
            if time.time() < self.cache_expiry and self.channels_cache:
                self.logger.debug("Using cached DistroTV channels")
                return self.channels_cache
            
            self.logger.info("Scraping DistroTV channels")
            channels = []
            
            # Get main live page
            html_content = self._get_page_content(self.live_url)
            
            if html_content:
                # Try BeautifulSoup first
                if BEAUTIFULSOUP_AVAILABLE:
                    self.logger.debug("Scraping with BeautifulSoup")
                    channels = self._scrape_with_beautifulsoup(html_content)
                
                # Fall back to regex if BeautifulSoup fails
                if not channels:
                    self.logger.debug("BeautifulSoup failed, trying regex")
                    channels = self._scrape_with_regex(html_content)
            
            # Try alternative URLs if main page fails
            if not channels:
                alternative_urls = [
                    "https://www.distro.tv/",
                    "https://distro.tv/live/",
                    "https://distro.tv/",
                ]
                
                for url in alternative_urls:
                    try:
                        self.logger.debug(f"Trying alternative URL: {url}")
                        html_content = self._get_page_content(url)
                        if html_content:
                            if BEAUTIFULSOUP_AVAILABLE:
                                channels = self._scrape_with_beautifulsoup(html_content)
                            if not channels:
                                channels = self._scrape_with_regex(html_content)
                            
                            if channels:
                                break
                    except Exception as e:
                        self.logger.debug(f"Alternative URL {url} failed: {e}")
                        continue
            
            # ABSOLUTE LAST RESORT: External M3U
            if not channels:
                self.logger.warning("All scraping methods failed, using external M3U as last resort")
                channels = self._get_external_m3u_fallback()
            
            # Validate and normalize channels
            valid_channels = []
            for channel in channels:
                if self.validate_channel(channel):
                    valid_channels.append(self.normalize_channel(channel))
            
            # Cache results
            if valid_channels:
                self.channels_cache = valid_channels
                self.cache_expiry = time.time() + self.cache_duration
                self.logger.info(f"Successfully processed {len(valid_channels)} DistroTV channels")
            else:
                self.logger.warning("No valid DistroTV channels found via any method")
            
            return valid_channels
            
        except Exception as e:
            self.logger.error(f"Error fetching DistroTV channels: {e}")
            # Try external M3U as absolute emergency fallback
            try:
                return self._get_external_m3u_fallback()
            except:
                return []