from aiohttp import ClientSession
import itertools
import math

from PIL import Image, UnidentifiedImageError
from requests import Session
import requests
from typing import List, Optional
from io import BytesIO
from ..dataclasses import Tile, Size

from . import api
from .panorama import StreetViewPanorama
from .parse import parse_coverage_tile_response, parse_panorama_id_response, \
    parse_panorama_radius_response
from .util import is_third_party_panoid
from ..geo import wgs84_to_tile_coord
from ..util import get_equirectangular_panorama, get_equirectangular_panorama_async

def find_panorama(lat: float, lon: float, radius: int = 50, locale: str = "en",
                  search_third_party: bool = False, session: Session = None) -> Optional[StreetViewPanorama]:
    """
    Searches for a panorama within a radius around a point.

    :param lat: Latitude of the center point.
    :param lon: Longitude of the center point.
    :param radius: *(optional)* Search radius in meters. Defaults to 50.
    :param locale: *(optional)* Desired language of the location's address as IETF code.
      Defaults to ``en``.
    :param search_third_party: *(optional)* Whether to search for third-party panoramas
      rather than official ones. Defaults to false.
    :param session: *(optional)* A requests session.
    :return: A StreetViewPanorama object if a panorama was found, or None.
    """
    response = api.find_panorama(lat, lon, radius=radius, download_depth=False,
                                 locale=locale, search_third_party=search_third_party, session=session)
    return parse_panorama_radius_response(response)

async def find_panorama_async(lat: float, lon: float, session: ClientSession, radius: int = 50,
                              locale: str = "en", search_third_party: bool = False) -> Optional[StreetViewPanorama]:
    response = await api.find_panorama_async(lat, lon, session, radius=radius, download_depth=False,
                                             locale=locale, search_third_party=search_third_party)
    return parse_panorama_radius_response(response)

def find_panorama_by_id(panoid: str, download_depth: bool = False, locale: str = "en",
                        session: Session = None) -> Optional[StreetViewPanorama]:
    """
    Fetches metadata of a specific panorama.

    :param panoid: The pano ID.
    :param download_depth: Whether to download and parse the depth map.
    :param locale: Desired language of the location's address as IETF code.
    :param session: *(optional)* A requests session.
    :return: A StreetViewPanorama object if a panorama with this ID exists, or None.
    """
    response = api.find_panorama_by_id(panoid, download_depth=download_depth,
                                       locale=locale, session=session)
    return parse_panorama_id_response(response)

async def find_panorama_by_id_async(panoid: str, session: ClientSession, download_depth: bool = False,
                                    locale: str = "en") -> Optional[StreetViewPanorama]:
    response = await api.find_panorama_by_id_async(panoid, session,
                                                   download_depth=download_depth, locale=locale)
    return parse_panorama_id_response(response)

def get_coverage_tile(tile_x: int, tile_y: int, session: Session = None) -> List[StreetViewPanorama]:
    """
    Fetches Street View coverage on a specific map tile. Coordinates are in Slippy Map aka XYZ format
    at zoom level 17.

    :param tile_x: X coordinate of the tile.
    :param tile_y: Y coordinate of the tile.
    :param session: *(optional)* A requests session.
    :return: A list of StreetViewPanoramas. If no coverage was returned by the API, the list is empty.
    """
    response = api.get_coverage_tile(tile_x, tile_y, session)
    return parse_coverage_tile_response(response)

async def get_coverage_tile_async(tile_x: int, tile_y: int, session: ClientSession) -> List[StreetViewPanorama]:
    response = await api.get_coverage_tile_async(tile_x, tile_y, session)
    return parse_coverage_tile_response(response)

def get_coverage_tile_by_latlon(lat: float, lon: float, session: Session = None) -> List[StreetViewPanorama]:
    """
    Same as :func:`get_coverage_tile <get_coverage_tile>`, but for fetching the tile on which a point is located.

    :param lat: Latitude of the point.
    :param lon: Longitude of the point.
    :param session: *(optional)* A requests session.
    :return: A list of StreetViewPanoramas. If no coverage was returned by the API, the list is empty.
    """
    tile_coord = wgs84_to_tile_coord(lat, lon, 17)
    return get_coverage_tile(tile_coord[0], tile_coord[1], session=session)

async def get_coverage_tile_by_latlon_async(lat: float, lon: float, session: ClientSession) \
        -> List[StreetViewPanorama]:
    tile_coord = wgs84_to_tile_coord(lat, lon, 17)
    return await get_coverage_tile_async(tile_coord[0], tile_coord[1], session)

def download_panorama(pano: StreetViewPanorama, path: str, zoom: int = 5, pil_args: dict = None) -> None:
    """
    Downloads a panorama to a file.

    :param pano: The panorama to download.
    :param path: Output path.
    :param zoom: (optional) Image size; 0 is lowest, 5 is highest. Defaults to 5.
    :param pil_args: (optional) Additional arguments for PIL's Image.save method. Defaults to {}.
    """
    if pil_args is None:
        pil_args = {}
    image = get_panorama(pano, zoom=zoom)
    if image:
        image.save(path, **pil_args)
    else:
        print(f"Failed to download panorama {pano.id}")

async def download_panorama_async(pano: StreetViewPanorama, path: str, session: ClientSession,
                                  zoom: int = 5, pil_args: dict = None) -> None:
    if pil_args is None:
        pil_args = {}
    image = await get_panorama_async(pano, session, zoom=zoom)
    if image:
        image.save(path, **pil_args)
    else:
        print(f"Failed to download panorama {pano.id}")

def get_panorama(pano: StreetViewPanorama, zoom: int = 5, session: Optional[Session] = None) -> Optional[Image.Image]:
    """
    Downloads a panorama and returns it as PIL image.

    :param pano: The panorama to download.
    :param zoom: (optional) Image size; 0 is lowest, 5 is highest. Defaults to 5.
    :param session: (optional) A requests session.
    :return: A PIL image containing the panorama, or None if no valid zoom level is found.
    """
    if pano.image_sizes:
        return _get_panorama_with_sizes(pano, zoom)
    else:
        return _get_panorama_without_sizes(pano, zoom, session)

def _get_panorama_with_sizes(pano: StreetViewPanorama, zoom: int) -> Optional[Image.Image]:
    zoom = max(0, min(zoom, len(pano.image_sizes) - 1))
    img_size = pano.image_sizes[zoom]
    tiles = _generate_tile_list(pano.id, zoom, (img_size.x, img_size.y))
    try:
        return get_equirectangular_panorama(img_size.x, img_size.y, pano.tile_size, tiles)
    except UnidentifiedImageError:
        print(f"Failed to download panorama {pano.id} at zoom level {zoom}")
        return None

def _get_panorama_without_sizes(pano: StreetViewPanorama, zoom: int, session: Optional[Session]) -> Optional[Image.Image]:
    ZOOM_LEVELS = range(zoom, -1, -1)  # From requested zoom to lowest (0)
    TILE_SIZE = Size(512, 512)  # Assuming a fixed tile size

    for test_zoom in ZOOM_LEVELS:
        img_size = _calculate_image_size(test_zoom)
        tiles = _generate_tile_list(pano.id, test_zoom, img_size)
        
        try:
            return get_equirectangular_panorama(img_size[0], img_size[1], TILE_SIZE, tiles)
        except UnidentifiedImageError:
            continue
    
    print(f"Failed to download panorama {pano.id} at any zoom level")
    return None

def _calculate_image_size(zoom: int) -> tuple:
    """Calculate the image size based on zoom level."""
    base_width, base_height = 416, 208  # Size at zoom level 0
    multiplier = 2 ** zoom
    return (base_width * multiplier, base_height * multiplier)

def _generate_tile_url(panoid: str, zoom: int, x: int, y: int) -> str:
    """Generate the URL for a specific tile."""
    if _is_third_party_panoid(panoid):
        return f"https://lh3.ggpht.com/p/{panoid}=x{x}-y{y}-z{zoom}"
    else:
        return f"https://cbk0.google.com/cbk?output=tile&panoid={panoid}&zoom={zoom}&x={x}&y={y}"

def _is_third_party_panoid(panoid: str) -> bool:
    """Check if the panoid is for a third-party panorama."""
    return not panoid.startswith("F:") and not panoid.startswith("C:")

def _generate_tile_list(panoid: str, zoom: int, img_size: tuple) -> List[Tile]:
    """Generate a list of tiles for the panorama."""
    tile_width, tile_height = 512, 512  # Assuming fixed tile size
    cols = -(-img_size[0] // tile_width)  # Ceiling division
    rows = -(-img_size[1] // tile_height)

    tiles = []
    for x in range(cols):
        for y in range(rows):
            url = _generate_tile_url(panoid, zoom, x, y)
            tiles.append(Tile(x, y, url))
    
    return tiles

def _download_tiles(tiles: List[Tile], session: Optional[Session]) -> dict:
    """Download all tiles and return them as a dictionary."""
    tile_images = {}
    for tile in tiles:
        response = session.get(tile.url) if session else requests.get(tile.url)
        if response.status_code == 200:
            tile_images[(tile.x, tile.y)] = response.content
        else:
            print(f"Failed to download tile at {tile.url}")
            tile_images[(tile.x, tile.y)] = None
    return tile_images

async def get_panorama_async(pano: StreetViewPanorama, session: ClientSession, zoom: int = 5) -> Optional[Image.Image]:
    # Implementation for async version...
    pass  # Placeholder for async implementation
