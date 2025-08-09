#!/usr/bin/env python3
"""
Unified Streaming Service Aggregator
Combines Xumo, Tubi, Plex, Pluto, and Samsung TV Plus into one service
"""

import os
import re
import json
import gzip
import time
import logging
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, Response, request
from gevent.pywsgi import WSGIServer # type: ignore
from gevent import monkey # type: ignore
import xml.etree.ElementTree as ET

# Import all provider classes
from providers.xumo_provider import XumoProvider
from providers.remaining_providers import PlexProvider, SamsungProvider
from providers.tubi_provider import TubiProvider
from providers.pluto_provider import PlutoProvider

monkey.patch_all()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class UnifiedStreamingAggregator:
    def __init__(self):
        self.app = Flask(__name__)
        self.providers = {}
        self.channels_cache = {}
        self.epg_cache = {}
        self.cache_expiry = {}
        self.cache_lock = threading.Lock()
        
        # Configuration from environment variables
        self.port = int(os.getenv('PORT', 7777))
        self.cache_duration = int(os.getenv('CACHE_DURATION', 3600))  # 1 hour default
        self.enabled_providers = os.getenv('ENABLED_PROVIDERS', 'all').split(',')
        
        # Filter configuration
        self.channel_name_include = os.getenv('CHANNEL_NAME_INCLUDE', '')
        self.channel_name_exclude = os.getenv('CHANNEL_NAME_EXCLUDE', '')
        self.group_include = os.getenv('GROUP_INCLUDE', '')
        self.group_exclude = os.getenv('GROUP_EXCLUDE', '')
        
        # Initialize providers
        self._init_providers()
        self._setup_routes()
        
    def _init_providers(self):
        """Initialize all available providers"""
        available_providers = {
            'xumo': XumoProvider,
            'tubi': TubiProvider,
            'plex': PlexProvider,
            'pluto': PlutoProvider,
            'samsung': SamsungProvider
        }
        
        for name, provider_class in available_providers.items():
            if self.enabled_providers == ['all'] or name in self.enabled_providers:
                try:
                    self.providers[name] = provider_class()
                    logger.info(f"Initialized {name} provider")
                except Exception as e:
                    logger.error(f"Failed to initialize {name} provider: {e}")
    
    def _setup_routes(self):
        """Setup Flask routes"""
        self.app.route('/playlist.m3u')(self.get_playlist)
        self.app.route('/epg.xml')(self.get_epg_xml)
        self.app.route('/epg.xml.gz')(self.get_epg_xml_gz)
        self.app.route('/channels.json')(self.get_channels_json)
        self.app.route('/status')(self.get_status)
        self.app.route('/clear_cache')(self.clear_cache)
        
    def _is_cache_valid(self, cache_key):
        """Check if cache is still valid"""
        return (cache_key in self.cache_expiry and 
                time.time() < self.cache_expiry[cache_key])
    
    def _apply_filters(self, channels):
        """Apply regex filters to channels"""
        filtered_channels = []
        
        for channel in channels:
            name = channel.get('name', '')
            group = channel.get('group', '')
            
            # Apply name filters
            if self.channel_name_include and not re.search(self.channel_name_include, name, re.IGNORECASE):
                continue
            if self.channel_name_exclude and re.search(self.channel_name_exclude, name, re.IGNORECASE):
                continue
                
            # Apply group filters  
            if self.group_include and not re.search(self.group_include, group, re.IGNORECASE):
                continue
            if self.group_exclude and re.search(self.group_exclude, group, re.IGNORECASE):
                continue
                
            filtered_channels.append(channel)
            
        return filtered_channels
    
    def _remove_duplicates(self, channels):
        """Remove duplicate channels based on name and stream URL"""
        seen = set()
        unique_channels = []
        
        for channel in channels:
            # Create a key based on normalized name and stream URL
            key = (
                channel.get('name', '').lower().strip(),
                channel.get('stream_url', '')
            )
            
            if key not in seen and key[0] and key[1]:  # Ensure name and URL exist
                seen.add(key)
                unique_channels.append(channel)
                
        logger.info(f"Removed {len(channels) - len(unique_channels)} duplicate channels")
        return unique_channels
    
    def _get_all_channels(self):
        """Get channels from all providers"""
        cache_key = 'all_channels'
        
        with self.cache_lock:
            if self._is_cache_valid(cache_key):
                return self.channels_cache[cache_key]
        
        all_channels = []
        channel_number = 1
        
        for provider_name, provider in self.providers.items():
            try:
                logger.info(f"Fetching channels from {provider_name}")
                provider_channels = provider.get_channels()
                
                if provider_channels:
                    # Add provider info and assign channel numbers
                    for channel in provider_channels:
                        channel['provider'] = provider_name
                        channel['channel_number'] = channel.get('number', channel_number)
                        channel_number += 1
                        
                    all_channels.extend(provider_channels)
                    logger.info(f"Got {len(provider_channels)} channels from {provider_name}")
                else:
                    logger.warning(f"No channels returned from {provider_name}")
                    
            except Exception as e:
                logger.error(f"Error fetching channels from {provider_name}: {e}")
        
        # Apply filters and remove duplicates
        all_channels = self._apply_filters(all_channels)
        all_channels = self._remove_duplicates(all_channels)
        
        # Sort by channel number
        all_channels.sort(key=lambda x: x.get('channel_number', 999999))
        
        # Cache the results
        with self.cache_lock:
            self.channels_cache[cache_key] = all_channels
            self.cache_expiry[cache_key] = time.time() + self.cache_duration
            
        logger.info(f"Total channels after filtering and deduplication: {len(all_channels)}")
        return all_channels
    
    def _get_all_epg_data(self):
        """Get EPG data from all providers"""
        cache_key = 'all_epg'
        
        with self.cache_lock:
            if self._is_cache_valid(cache_key):
                return self.epg_cache[cache_key]
        
        all_epg_data = {}
        
        for provider_name, provider in self.providers.items():
            try:
                logger.info(f"Fetching EPG data from {provider_name}")
                provider_epg = provider.get_epg_data()
                
                if provider_epg:
                    all_epg_data.update(provider_epg)
                    logger.info(f"Got EPG data for {len(provider_epg)} channels from {provider_name}")
                    
            except Exception as e:
                logger.error(f"Error fetching EPG data from {provider_name}: {e}")
        
        # Cache the results
        with self.cache_lock:
            self.epg_cache[cache_key] = all_epg_data
            self.cache_expiry[cache_key] = time.time() + self.cache_duration
            
        return all_epg_data
    
    def get_playlist(self):
        """Generate M3U playlist"""
        try:
            channels = self._get_all_channels()
            
            # Build M3U content
            m3u_lines = ['#EXTM3U']
            
            for channel in channels:
                # Build EXTINF line
                extinf_parts = [f"#EXTINF:-1"]
                
                # Add attributes
                if channel.get('id'):
                    extinf_parts.append(f'tvg-id="{channel["id"]}"')
                if channel.get('name'):
                    extinf_parts.append(f'tvg-name="{channel["name"]}"')
                if channel.get('logo'):
                    extinf_parts.append(f'tvg-logo="{channel["logo"]}"')
                if channel.get('group'):
                    extinf_parts.append(f'group-title="{channel["group"]}"')
                if channel.get('channel_number'):
                    extinf_parts.append(f'tvg-chno="{channel["channel_number"]}"')
                if channel.get('provider'):
                    extinf_parts.append(f'provider="{channel["provider"]}"')
                    
                extinf_line = ' '.join(extinf_parts) + f',{channel.get("name", "Unknown")}'
                m3u_lines.append(extinf_line)
                m3u_lines.append(channel.get('stream_url', ''))
                m3u_lines.append('')  # Empty line between channels
            
            m3u_content = '\n'.join(m3u_lines)
            
            return Response(
                m3u_content,
                mimetype='application/vnd.apple.mpegurl',
                headers={'Content-Disposition': 'attachment; filename=playlist.m3u'}
            )
            
        except Exception as e:
            logger.error(f"Error generating playlist: {e}")
            return Response(f"Error generating playlist: {e}", status=500)
    
    def get_epg_xml(self):
        """Generate EPG XML"""
        try:
            channels = self._get_all_channels()
            epg_data = self._get_all_epg_data()
            
            # Create XML structure
            root = ET.Element('tv')
            root.set('generator-info-name', 'Unified Streaming Aggregator')
            
            # Add channel elements
            for channel in channels:
                channel_elem = ET.SubElement(root, 'channel')
                channel_elem.set('id', str(channel.get('id', '')))
                
                display_name = ET.SubElement(channel_elem, 'display-name')
                display_name.text = channel.get('name', '')
                
                if channel.get('logo'):
                    icon = ET.SubElement(channel_elem, 'icon')
                    icon.set('src', channel['logo'])
            
            # Add programme elements
            for channel_id, programmes in epg_data.items():
                for programme in programmes:
                    prog_elem = ET.SubElement(root, 'programme')
                    prog_elem.set('channel', str(channel_id))
                    prog_elem.set('start', programme.get('start', ''))
                    prog_elem.set('stop', programme.get('stop', ''))
                    
                    if programme.get('title'):
                        title = ET.SubElement(prog_elem, 'title')
                        title.text = programme['title']
                    
                    if programme.get('description'):
                        desc = ET.SubElement(prog_elem, 'desc')
                        desc.text = programme['description']
            
            # Convert to string
            xml_str = ET.tostring(root, encoding='unicode', method='xml')
            xml_content = f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE tv SYSTEM "xmltv.dtd">\n{xml_str}'
            
            return Response(
                xml_content,
                mimetype='application/xml',
                headers={'Content-Disposition': 'attachment; filename=epg.xml'}
            )
            
        except Exception as e:
            logger.error(f"Error generating EPG XML: {e}")
            return Response(f"Error generating EPG XML: {e}", status=500)
    
    def get_epg_xml_gz(self):
        """Generate compressed EPG XML"""
        try:
            # Get the XML content
            xml_response = self.get_epg_xml()
            xml_content = xml_response.get_data(as_text=True)
            
            # Compress it
            compressed_data = gzip.compress(xml_content.encode('utf-8'))
            
            return Response(
                compressed_data,
                mimetype='application/gzip',
                headers={'Content-Disposition': 'attachment; filename=epg.xml.gz'}
            )
            
        except Exception as e:
            logger.error(f"Error generating compressed EPG: {e}")
            return Response(f"Error generating compressed EPG: {e}", status=500)
    
    def get_channels_json(self):
        """Return channels as JSON"""
        try:
            channels = self._get_all_channels()
            return Response(
                json.dumps(channels, indent=2),
                mimetype='application/json'
            )
        except Exception as e:
            logger.error(f"Error generating channels JSON: {e}")
            return Response(f"Error generating channels JSON: {e}", status=500)
    
    def get_status(self):
        """Return status page"""
        channels = self._get_all_channels()
        provider_stats = {}
        
        for channel in channels:
            provider = channel.get('provider', 'unknown')
            provider_stats[provider] = provider_stats.get(provider, 0) + 1
        
        status_html = f"""
        <html>
        <head><title>Unified Streaming Aggregator Status</title></head>
        <body>
            <h1>Unified Streaming Aggregator</h1>
            <h2>Status</h2>
            <p>Total Channels: {len(channels)}</p>
            <h3>Provider Statistics:</h3>
            <ul>
        """
        
        for provider, count in provider_stats.items():
            status_html += f"<li>{provider}: {count} channels</li>"
        
        status_html += """
            </ul>
            <h3>Endpoints:</h3>
            <ul>
                <li><a href="/playlist.m3u">M3U Playlist</a></li>
                <li><a href="/epg.xml">EPG XML</a></li>
                <li><a href="/epg.xml.gz">EPG XML (Compressed)</a></li>
                <li><a href="/channels.json">Channels JSON</a></li>
                <li><a href="/clear_cache">Clear Cache</a></li>
            </ul>
        </body>
        </html>
        """
        
        return Response(status_html, mimetype='text/html')
    
    def clear_cache(self):
        """Clear all caches"""
        with self.cache_lock:
            self.channels_cache.clear()
            self.epg_cache.clear()
            self.cache_expiry.clear()
            
        return Response("Cache cleared successfully", mimetype='text/plain')
    
    def run(self):
        """Start the server"""
        logger.info(f"Starting Unified Streaming Aggregator on port {self.port}")
        logger.info(f"Enabled providers: {list(self.providers.keys())}")
        
        try:
            server = WSGIServer(('0.0.0.0', self.port), self.app, log=None)
            server.serve_forever()
        except Exception as e:
            logger.error(f"Server error: {e}")
            raise

if __name__ == '__main__':
    app = UnifiedStreamingAggregator()
    app.run()