from aiohttp import ClientSession
import itertools
import math
from PIL import Image
from requests import Session
from typing import List, Optional

from . import api
from .panorama import StreetViewPanorama
from .parse import parse_coverage_tile_response, parse_panorama_id_response, \
    parse_panorama_radius_response
from .util import is_third_party_panoid
from ..dataclasses import Tile
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

    # TODO
    # the `SingleImageSearch` call returns a different kind of depth data
    # than `photometa`; need to deal with that at some point

    response = api.find_panorama(lat, lon, radius=radius, download_depth=False,
                                 locale=locale, search_third_party=search_third_party, session=session)
    return parse_panorama_radius_response(response)


async def find_panorama_async(lat: float, lon: float, session: ClientSession, radius: int = 50,
                              locale: str = "en", search_third_party: bool = False) -> Optional[StreetViewPanorama]:
    # TODO
    # the `SingleImageSearch` call returns a different kind of depth data
    # than `photometa`; need to deal with that at some point
    response = await api.find_panorama_async(lat, lon, session, radius=radius, download_depth=False,
                                             locale=locale, search_third_party=search_third_party)
    return parse_panorama_radius_response(response)


def find_panorama_by_id(panoid: str, download_depth: bool = False, locale: str = "en",
                        session: Session = None) -> Optional[StreetViewPanorama]:
    """
    Fetches metadata of a specific panorama.

    Unfortunately, `as mentioned on this page
    <https://developers.google.com/maps/documentation/tile/streetview#panoid_response>`_,
    pano IDs are not stable, so a request that works today may return nothing a few months into the future.

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

    When viewing Google Maps with satellite imagery in globe view and zooming into a spot,
    it makes this API call. This is useful because 1) it allows for fetching coverage for a whole area, and
    2) there are various hidden/removed locations which cannot be found by any other method
    (unless you access them by pano ID directly).

    This function returns ID, position, elevation, orientation, and links within the tile of the most recent coverage.
    The rest of the metadata, such as historical panoramas or links across tiles, must be fetched manually one by one.

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
    :param zoom: *(optional)* Image size; 0 is lowest, 5 is highest. The dimensions of a zoom level of a
        specific panorama depend on the camera used. If the requested zoom level does not exist,
        the highest available level will be downloaded. Defaults to 5.
    :param pil_args: *(optional)* Additional arguments for PIL's
        `Image.save <https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.save>`_
        method, e.g. ``{"quality":100}``. Defaults to ``{}``.
    """
    if pil_args is None:
        pil_args = {}
    image = get_panorama(pano, zoom=zoom)
    image.save(path, **pil_args)


async def download_panorama_async(pano: StreetViewPanorama, path: str, session: ClientSession,
                                  zoom: int = 5, pil_args: dict = None) -> None:
    if pil_args is None:
        pil_args = {}
    image = await get_panorama_async(pano, session, zoom=zoom)
    image.save(path, **pil_args)

def _find_highest_zoom(panoid: str, max_zoom: int, session: Session = None) -> tuple:
    """Find the highest available zoom level for a panorama."""
    for zoom in range(max_zoom, -1, -1):
        img_size = _calculate_image_size(zoom)
        test_tile_url = _generate_tile_url(panoid, zoom, 0, 0)
        response = session.get(test_tile_url) if session else requests.get(test_tile_url)
        
        if response.status_code == 200:
            return zoom, img_size
    
    return None, None

def _calculate_image_size(zoom: int) -> tuple:
    """Calculate the image size based on zoom level."""
    base_width, base_height = 416, 208  # Size at zoom level 0
    multiplier = 2 ** zoom
    return (base_width * multiplier, base_height * multiplier)

def get_panorama(pano: StreetViewPanorama, zoom: int = 5, session: Optional[requests.Session] = None) -> Optional[Image.Image]:
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

def _get_panorama_with_sizes(pano: StreetViewPanorama, zoom: int) -> Image.Image:
    zoom = max(0, min(zoom, len(pano.image_sizes) - 1))
    img_size = pano.image_sizes[zoom]
    tiles = _generate_tile_list(pano.id, zoom, (img_size.x, img_size.y))
    return get_equirectangular_panorama(img_size.x, img_size.y, pano.tile_size, tiles)

def _get_panorama_without_sizes(pano: StreetViewPanorama, zoom: int, session: Optional[requests.Session]) -> Optional[Image.Image]:
    ZOOM_LEVELS = range(5, -1, -1)  # From highest (5) to lowest (0)
    TILE_SIZE = (512, 512)  # Assuming a fixed tile size

    for test_zoom in ZOOM_LEVELS:
        if test_zoom <= zoom:
            # Test if the zoom level exists by trying to download a tile
            test_tile_url = _generate_tile_url(pano.id, test_zoom, 0, 0)
            response = session.get(test_tile_url) if session else requests.get(test_tile_url)
            
            if response.status_code == 200:
                # This zoom level exists, so we'll use it
                img_size = _calculate_image_size(test_zoom)
                tiles = _generate_tile_list(pano.id, test_zoom, img_size)
                return get_equirectangular_panorama(img_size[0], img_size[1], TILE_SIZE, tiles)
    
    # If we've reached this point, no valid zoom level was found
    return None

async def get_panorama_async(pano: StreetViewPanorama, session: ClientSession, zoom: int = 5) -> Image.Image:
    zoom = _validate_get_panorama_params(pano, zoom)
    return await get_equirectangular_panorama_async(
        pano.image_sizes[zoom].x, pano.image_sizes[zoom].y,
        pano.tile_size, _generate_tile_list(pano, zoom),
        session)


def _validate_get_panorama_params(pano: StreetViewPanorama, zoom: int) -> int:
    if not pano.image_sizes:
        raise ValueError("pano.image_sizes is None.")
    zoom = max(0, min(zoom, len(pano.image_sizes) - 1))
    return zoom


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
