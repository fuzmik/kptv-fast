# KPTV FAST Streams

A high-performance streaming service aggregator that combines multiple free streaming platforms into a single M3U playlist and EPG. Perfect for use with Channels DVR, Plex, or any IPTV client.

## 🎯 Overview

This application aggregates live TV channels from multiple streaming services into a unified playlist, making it easy to access thousands of free channels through your favorite IPTV client.

## ✨ Features

- **5 Streaming Providers**: Xumo, Tubi, Plex, Pluto TV, and Samsung TV Plus
- **High Performance**: Concurrent channel fetching with ~15-20 second startup time
- **Smart Caching**: 2-hour cache with background refresh to keep channels ready
- **Duplicate Removal**: Automatically removes duplicate channels across providers
- **Flexible Filtering**: Regex-based channel and group filtering
- **Multiple Formats**: M3U playlist, XMLTV EPG, and JSON channel data
- **Debug Mode**: Comprehensive logging for troubleshooting
- **Health Monitoring**: Built-in health checks and status endpoints
- **Docker Ready**: Fully containerized with Docker Compose

## 📺 Supported Providers

| Provider | Channels* | Authentication | Notes |
|----------|-----------|----------------|-------|
| **Pluto TV** | ~400 | None | Largest selection, reliable |
| **Plex** | ~650 | None | High-quality channels |
| **Samsung TV Plus** | ~420 | None | Good variety |
| **Xumo** | ~85 | None | Optimized for speed |
| **Tubi** | ~50+ | None | Anonymous access |

*Channel counts are approximate and vary by region

## 🚀 Quick Start

### Docker Compose (Recommended)

1. **Create docker-compose.yml:**
```yaml
version: '3.8'

services:
  unified-streaming:
    image: ghcr.io/kpirnie/kptv-fast:latest
    ports:
      - "7777:7777"
    environment:
      - DEBUG=false
      - CACHE_DURATION=7200
      - WARM_CACHE_ON_STARTUP=true
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:7777/status"]
      interval: 30s
      timeout: 10s
      retries: 3
```

2. **Start the service:**
```bash
docker-compose up -d
```

3. **Access your content:**
   - Status page: `http://localhost:7777/status`
   - M3U playlist: `http://localhost:7777/playlist`
   - EPG: `http://localhost:7777/epg`
   - EPG GZ: `http://localhost:7777/epggz`

### Manual Build

```bash
git clone https://github.com/kpirnie/kptv-fast
cd kptv-fast
docker-compose build
docker-compose up -d
```

## ⚙️ Configuration

### Environment Variables

#### Basic Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `7777` | HTTP server port |
| `DEBUG` | `false` | Enable verbose logging |
| `ENABLED_PROVIDERS` | `all` | Comma-separated list of providers to enable |

#### Performance Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_DURATION` | `7200` | Cache duration in seconds (2 hours) |
| `MAX_WORKERS` | `5` | Concurrent provider fetching threads |
| `PROVIDER_TIMEOUT` | `60` | Per-provider timeout in seconds |

#### Startup Optimization
| Variable | Default | Description |
|----------|---------|-------------|
| `WARM_CACHE_ON_STARTUP` | `true` | Pre-load channels on startup |
| `STARTUP_CACHE_DELAY` | `10` | Delay before cache warming (seconds) |
| `WARM_EPG_ON_STARTUP` | `false` | Also pre-load EPG data |

#### Content Filtering
| Variable | Default | Description |
|----------|---------|-------------|
| `CHANNEL_NAME_INCLUDE` | `""` | Regex to include channels by name |
| `CHANNEL_NAME_EXCLUDE` | `""` | Regex to exclude channels by name |
| `GROUP_INCLUDE` | `""` | Regex to include channels by group |
| `GROUP_EXCLUDE` | `""` | Regex to exclude channels by group |

#### Provider-Specific Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `PLUTO_REGION` | `us_west` | Pluto TV region (us_west, us_east, uk, ca, fr) |
| `PLEX_REGION` | `local` | Plex region |
| `SAMSUNG_REGION` | `us` | Samsung TV Plus region |

### Example Configurations

#### Basic Setup
```yaml
environment:
  - PORT=7777
  - DEBUG=false
  - CACHE_DURATION=7200
```

#### Performance Optimized
```yaml
environment:
  - MAX_WORKERS=8
  - PROVIDER_TIMEOUT=45
  - WARM_CACHE_ON_STARTUP=true
  - STARTUP_CACHE_DELAY=5
```

#### Filtered Setup (News Channels Only)
```yaml
environment:
  - CHANNEL_NAME_INCLUDE="news|cnn|fox|msnbc"
  - CACHE_DURATION=3600
```

#### Specific Providers Only
```yaml
environment:
  - ENABLED_PROVIDERS=pluto,plex,samsung
```

## 🌐 API Endpoints

### Content Endpoints
- **`GET /playlist`** - M3U8 playlist with all channels
- **`GET /epg`** - XMLTV EPG data
- **`GET /epggz`** - Compressed XMLTV EPG data
- **`GET /channels`** - JSON formatted channel list

### Management Endpoints
- **`GET /status`** - HTML status page with statistics
- **`GET /debug`** - JSON debug information
- **`GET /refresh`** - Force cache refresh: set a cronjob to curl/wget this endpoint to setup a regular refresh
- **`GET /clear_cache`** - Clear all cached data

### Status Page
The status page (`/status`) provides:
- Total channel count
- Per-provider statistics
- Cache status
- Performance metrics
- Quick links to all endpoints

## 📊 Performance

### Typical Performance Metrics
- **Startup Time**: 15-20 seconds with cache warming
- **First Request**: Instant (with cache warming enabled)
- **Subsequent Requests**: <100ms (cached)
- **Memory Usage**: ~200-300MB
- **CPU Usage**: Low (mostly I/O bound)

### Optimization Tips

1. **Enable Cache Warming**: Set `WARM_CACHE_ON_STARTUP=true`
2. **Tune Worker Count**: Adjust `MAX_WORKERS` based on your server
3. **Regional Optimization**: Use closer regions for better performance
4. **Filter Channels**: Use regex filters to reduce channel count
5. **Monitor Debug Logs**: Use `DEBUG=true` to identify slow providers

## 🔧 Troubleshooting

### Common Issues

#### No Channels Loading
```bash
# Check provider status
curl http://localhost:7777/debug

# Check logs
docker-compose logs -f kptv-fast

# Force refresh
curl http://localhost:7777/refresh
```

#### Slow Performance
```bash
# Enable debug logging
docker-compose down
# Set DEBUG=true in docker-compose.yml
docker-compose up -d

# Check which provider is slow
docker-compose logs -f kptv-fast
```

#### Provider-Specific Issues

**Pluto TV**: DNS resolution issues
```yaml
# Add to docker-compose.yml
dns:
  - 8.8.8.8
  - 8.8.4.4
```

**Xumo**: Timeout issues
```yaml
environment:
  - PROVIDER_TIMEOUT=90  # Increase timeout
```

**Tubi**: BeautifulSoup parsing issues
```bash
# Rebuild with updated requirements
docker-compose build --no-cache
```

### Debug Mode

Enable comprehensive logging:
```yaml
environment:
  - DEBUG=true
```

This provides:
- Function-level logging
- Performance timings
- Error stack traces
- Provider-specific debug info

### Health Checks

The application includes built-in health monitoring:
```bash
# Check health
curl http://localhost:7777/status

# Docker health check
docker-compose ps
```

## 🏗️ Architecture

### Components
- **Flask Web Server**: HTTP API and status endpoints
- **Provider System**: Modular provider architecture
- **Caching Layer**: Redis-like in-memory caching with TTL
- **Background Tasks**: Cache warming and refresh threads
- **Concurrent Processing**: ThreadPoolExecutor for parallel fetching

### Provider Architecture
Each provider implements:
- `get_channels()`: Fetch channel list
- `get_epg_data()`: Fetch EPG data (optional)
- Built-in validation and normalization
- Error handling and logging

## 🤝 Integration Examples

### Channels DVR
1. Add source in Channels DVR
2. Use M3U URL: `http://your-server:7777/playlist`
3. Use EPG URL: `http://your-server:7777/epg`

### Plex
1. Install the IPTV plugin
2. Configure with M3U URL
3. Set EPG source

### VLC
```bash
vlc http://your-server:7777/playlist
```

### Kodi
1. Install PVR IPTV Simple Client
2. Set M3U path to your server URL
3. Configure EPG source

## 📝 Logging

### Log Levels
- **INFO**: General operations and status
- **WARNING**: Non-critical issues
- **ERROR**: Critical failures
- **DEBUG**: Detailed troubleshooting info

### Log Format
```
Production (DEBUG=false):
2025-08-09 13:00:00 - INFO - 🚀 1794 channels ready in 15.2s

Debug (DEBUG=true):
2025-08-09 13:00:00 - providers.pluto - DEBUG - _get_session_token:45 - Got new session token
```

## 🔒 Security

### Best Practices
- Run as non-root user (built into Docker image)
- Use reverse proxy for external access
- Enable health checks
- Monitor logs for unusual activity
- Keep Docker images updated

### Network Security
```yaml
# Restrict to local network
ports:
  - "127.0.0.1:7777:7777"

# Or use reverse proxy
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.streaming.rule=Host(`streaming.local`)"
```

## 📈 Monitoring

### Prometheus Metrics (Future Enhancement)
The application is designed to support metrics collection:
- Channel count per provider
- Request response times
- Cache hit/miss ratios
- Provider success rates

### Log Aggregation
For production deployments, consider:
- ELK Stack for log analysis
- Grafana for visualization
- Alert manager for notifications

## 🛠️ Development

### Local Development
```bash
# Clone repository
git clone https://github.com/kpirnie/kptv-fast
cd kptv-fast

# Install dependencies
pip install -r requirements.txt

# Run locally
DEBUG=true python app.py
```

### Adding New Providers
1. Create new provider class inheriting from `BaseProvider`
2. Implement `get_channels()` and `get_epg_data()` methods
3. Add to provider imports in `app.py`
4. Test with debug mode enabled

### Contributing
1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Submit pull request

## 📄 License

MIT License - see LICENSE file for details.

## 🙏 Acknowledgments

- https://github.com/jgomez177 - Inspiration for Tubi, Plex, & Pluto implementations
- https://github.com/BuddyChewChew - Inspiration for the Xumo implementation
- https://github.com/matthuisman - Inspiration for the Samsung TVPlus implementation
- All the streaming services for providing free content
- The open-source community for the excellent libraries used

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/kpirnie/kptv-fast/issues)

---

**⭐ If this project helps you, please give it a star on GitHub!**