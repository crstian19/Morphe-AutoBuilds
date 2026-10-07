import json
import logging 

from src import session, flaresolverr 
from bs4 import BeautifulSoup

# Define a standard browser User-Agent to avoid 403 Forbidden errors
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://apkpure.net/'
}

def get_latest_version(app_name: str, config: str) -> str: 
    url = f"https://apkpure.net/{config['name']}/{config['package']}/versions"

    try:
        # Added headers to the request
        response = flaresolverr.get_with_bypass(url, session=session, headers=HEADERS, timeout=60) or session.get(url, headers=HEADERS)
        response.raise_for_status()
        
        content_size = len(response.content)
        logging.info(f"URL:{response.url} [{content_size}/{content_size}] -> \"-\" [1]")
        
        soup = BeautifulSoup(response.content, "html.parser")
        version_info = soup.find('div', class_='ver-top-down')

        if version_info and 'data-dt-version' in version_info.attrs:
            return version_info['data-dt-version']
            
    except Exception as e:
        logging.error(f"Failed to fetch latest version for {app_name}: {e}")
        
    return None

def get_download_link(version: str, app_name: str, config: str) -> str:
    # APKPure often uses a specific structure for download pages
    url = f"https://apkpure.net/{config['name']}/{config['package']}/download/{version}"

    try:
        response = flaresolverr.get_with_bypass(url, session=session, headers=HEADERS, timeout=60) or session.get(url, headers=HEADERS)
        response.raise_for_status()
        
        content_size = len(response.content)
        logging.info(f"URL:{response.url} [{content_size}/{content_size}] -> \"-\" [1]")
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Look for the download link; APKPure sometimes uses 'download_link' or 'fast-download'
        download_link = soup.find('a', id='download_link')
        if download_link and download_link.get('href'):
            href = download_link['href']
            # If it's a relative URL, it's the direct link; if it's a page, extract from it
            if 'd.apkpure.com' in href:
                return href
        
        # Fallback: regex search for direct d.apkpure.com links (adapted from morphe-apps-builder)
        import re
        html = response.text
        match = re.search(r'href="(https://d\.apkpure\.com/b/(?:XAPK|APK)/[^"]+)"', html)
        if match:
            dl_url = match.group(1).replace("&amp;", "&")
            logging.info(f"APKPure direct link found via regex for {app_name}")
            return dl_url
            
    except Exception as e:
        logging.error(f"Failed to fetch download link for {app_name} v{version}: {e}")
    
    return None
