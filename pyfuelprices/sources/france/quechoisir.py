"""QUECHOISIR data source."""
import logging
import json

import aiohttp

from geopy import distance

from pyfuelprices.fuel_locations import Fuel, FuelLocation

from pyfuelprices.const import (
    PROP_AREA_LAT,
    PROP_AREA_LONG,
    PROP_FUEL_LOCATION_SOURCE,
    PROP_FUEL_LOCATION_PREVENT_CACHE_CLEANUP,
    PROP_FUEL_LOCATION_SOURCE_ID
)
from pyfuelprices.helpers import geocode_reverse_lookup
from pyfuelprices.sources import Source

from .const import QUECHOISIR_API_HEADERS, QUECHOISIR_API_GET_GAS_STATION, QUECHOISIR_API_LOOKUP_POSTCODE

_LOGGER = logging.getLogger(__name__)

class QuechoisirSource(Source):
    """Quechoisir FR data source."""
    provider_name = "quechoisir"
    location_cache = {}

    async def _send_request(self, url, form_data: dict) -> str:
        """Send a request to the API and return the raw response."""
        _LOGGER.debug("Sending HTTP request to Quechoisir with URL %s", url)
        with aiohttp.MultipartWriter("form-data") as mp:
            for k, v in form_data.items():
                part = mp.append(v)
                part.set_content_disposition("form-data", name=k)
            async with self._client_session.post(url=url,
                                                headers=QUECHOISIR_API_HEADERS,
                                                data=mp) as response:
                if response.ok:
                    return await response.text()
                _LOGGER.error("Error sending request to %s: %s - %s",
                                url,
                                response,
                                await response.text())

    async def lookup_commune_id(self, postcode: str) -> str:
        """Return the commune ID for a postcode."""
        response = await self._send_request(
            url=QUECHOISIR_API_LOOKUP_POSTCODE,
            form_data={
                "keyword": postcode,
                "field_name": "zipCodeOrCity"
            }
        )
        if response is not None:
            data = json.loads(response)
            if len(data) > 0:
                return data[0]["fieldIdToUpdateValue"]

    async def update(self, areas=None, force=False) -> list[FuelLocation]:
        """Custom update handler as this needs to query Quechoisir on areas."""
        self._configured_areas=[] if areas is None else areas
        for area in self._configured_areas:
            geocode = await geocode_reverse_lookup((area[PROP_AREA_LAT], area[PROP_AREA_LONG]))
            if geocode is not None:
                if geocode.raw["address"]["country_code"] != "fr":
                    _LOGGER.debug("Ignoring area %s as not in france")
                    continue
                _LOGGER.debug("Searching Quechoisir for FuelLocations at %s", area)
                # first get communeId
                cid = await self.lookup_commune_id(geocode.raw["address"]["postcode"])
                if cid is None:
                    _LOGGER.debug("Ignoring area %s as no commune ID was found.", area)
                    continue
                # now do API lookup
                data = await self._send_request(
                    url=QUECHOISIR_API_GET_GAS_STATION,
                    form_data={
                        "zipCodeOrCity": geocode.raw["address"]["postcode"],
                        "communeId": cid,
                        "radius": "30",
                        "fuelList": "3"
                    }
                )
                if data is None:
                    continue
                data = json.loads(data)


    async def parse_raw_fuel_station(self, station) -> FuelLocation:
        """Converts a raw instance of a fuel station into a fuel location."""
        site_id = f"{self.provider_name}_{station['id']}"
        _LOGGER.debug("Parsing Quechoisir location ID %s", site_id)
        loc = FuelLocation.create(
            site_id=site_id,
            name=f"{station['nom']}",
            address=station["adresse"],
            lat=station["lat"],
            long=station["lon"],
            brand="Unknown",
            available_fuels=self.parse_fuels(station["carburants"]),
            postal_code="See address",
            currency="EUR",
            props={
                "data": station,
                PROP_FUEL_LOCATION_PREVENT_CACHE_CLEANUP: True,
                PROP_FUEL_LOCATION_SOURCE: self.provider_name,
                PROP_FUEL_LOCATION_SOURCE_ID: station["id"]
            },
            next_update=self.next_update
        )
        if site_id not in self.location_cache:
            self.location_cache[site_id] = loc
        else:
            await self.location_cache[site_id].update(loc)
        return self.location_cache[site_id]

    async def parse_response(self, response) -> list[FuelLocation]:
        for station in response["carburants"]["carburant"]:
            await self.parse_raw_fuel_station(station)
        return list(self.location_cache.values())

    def parse_fuels(self, fuels) -> list[Fuel]:
        """Parse fuels from fuel_products."""
        fuel_parsed = []
        for fuel in fuels:
            try:
                cost = float(str(fuel["prix"]).replace(",", "")) / 1000
                fuel_parsed.append(
                    Fuel(
                        fuel_type=fuel["nom"],
                        cost=cost,
                        props=fuel
                    )
                )
            except ValueError:
                continue
        return fuel_parsed

    async def search_sites(self, coordinates, radius: float) -> list[dict]:
        """Return all available sites within a given radius."""
        # first query the API to populate cache / update data in case this data is unavailable.
        await self.update(
            areas=[{
                PROP_AREA_LAT: coordinates[0],
                PROP_AREA_LONG: coordinates[1]
            }]
        )
        locations = []
        for site in self.location_cache.values():
            dist = distance.distance(coordinates,
                                 (
                                    site.lat,
                                    site.long
                                )).miles
            if dist < radius:
                locations.append({
                    **site.__dict__(),
                    "distance": dist
                })
        return locations
