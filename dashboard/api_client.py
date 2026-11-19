import requests

from config import API_BASE_URL, REQUEST_TIMEOUT_SECONDS


class ApiError(Exception):
    """Raised when the backend is unreachable or returns an error."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _admin_headers(admin_id: str | None) -> dict:
    # The temporary identity header from Phase 3 (section 4.7).
    return {"X-Admin-Id": admin_id} if admin_id else {}


def _handle_response(response: requests.Response):
    if response.ok:
        return response.json()

    try:
        detail = response.json().get("detail", "Request failed.")
    except ValueError:
        detail = "Request failed."

    # FastAPI returns a list of field errors for 422 responses.
    if isinstance(detail, list):
        detail = "; ".join(item.get("msg", "Invalid input.") for item in detail)

    raise ApiError(response.status_code, str(detail))


def get(path: str, params: dict | None = None, admin_id: str | None = None):
    try:
        response = requests.get(
            f"{API_BASE_URL}{path}",
            params=params,
            headers=_admin_headers(admin_id),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        raise ApiError(0, f"Cannot reach the API at {API_BASE_URL}. Is the backend running?")
    return _handle_response(response)


def post(path: str, admin_id: str | None, payload: dict | None = None):
    try:
        response = requests.post(
            f"{API_BASE_URL}{path}",
            json=payload or {},
            headers=_admin_headers(admin_id),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        raise ApiError(0, f"Cannot reach the API at {API_BASE_URL}. Is the backend running?")
    return _handle_response(response)