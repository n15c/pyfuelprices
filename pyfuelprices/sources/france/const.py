"""France fuel sources consts."""

from pyfuelprices.const import DESKTOP_USER_AGENT

QUECHOISIR_API_BASE = "https://www.quechoisir.org/ajax"
QUECHOISIR_API_HEADERS = {
    "Content-Type": "multipart/form-data",
    "Accept": "*/*",
    "Referer": "https://www.quechoisir.org",
    "Origin": "https://www.quechoisir.org",
    "Connection": "keep-alive",
    "User-Agent": DESKTOP_USER_AGENT
}

QUECHOISIR_API_GET_GAS_STATION = (
    f"{QUECHOISIR_API_BASE}"
    "/carte/carburants"
    "/get_gas_station.php")
QUECHOISIR_API_LOOKUP_POSTCODE = (
    f"{QUECHOISIR_API_BASE}"
    "/autocomplete/zipcodeorcity/"
)
