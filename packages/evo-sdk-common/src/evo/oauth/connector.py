#  Copyright © 2025 Bentley Systems, Incorporated
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#      http://www.apache.org/licenses/LICENSE-2.0
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from __future__ import annotations

from types import TracebackType
from typing import Literal, Type, TypeVar

from pydantic import ValidationError

from evo import logging
from evo.common import APIConnector, RequestMethod
from evo.common.exceptions import EvoAPIException
from evo.common.interfaces import ITransport

from .data import AccessToken
from .exceptions import OAuthError

logger = logging.getLogger("oauth")

__all__ = ["OAuthConnector"]

T = TypeVar("T", bound=AccessToken)

DEFAULT_BASE_URI = "https://ims.bentley.com"


class OAuthConnector:
    """OAuth connector, used to authenticate with an OAuth server and obtain or refresh an access token.

    https://developer.bentley.com/apis/overview/authorization/
    """

    def __init__(
        self,
        transport: ITransport,
        client_id: str,
        client_secret: str | None = None,
        base_uri: str = DEFAULT_BASE_URI,
    ) -> None:
        """
        :param transport: The transport to use for making requests.
        :param client_id: The OAuth client ID, as registered with the OAuth provider.
        :param client_secret: The OAuth client secret, as registered with the OAuth provider. Only used for client credentials grant types.
        :param base_uri: The base URI of the OAuth server, defaults to ims.bentley.com.

        :raises OAuthError: If the issuer URL is invalid.
        """
        self._connector = APIConnector(base_uri, transport)
        self.__client_id = client_id
        self.__client_secret = client_secret

    def endpoint(self, endpoint_type: Literal["authorize", "token"]) -> str:
        """
        Returns the relevant OAuth endpoint by endpoint type. Possible values: "authorize", "token".
        """
        match endpoint_type:
            case "authorize":
                return "/connect/authorize"
            case "token":
                return "/connect/token"
        raise OAuthError("Invalid endpoint type provided. Available: authorize, token")

    @property
    def base_uri(self) -> str:
        return self._connector.base_url.rstrip("/")

    @property
    def client_id(self) -> str:
        return self.__client_id

    async def __aenter__(self) -> OAuthConnector:
        await self._connector.open()
        return self

    async def __aexit__(
        self, exc_type: type[Exception] | None, exc_value: Exception | None, traceback: TracebackType | None
    ) -> None:
        await self._connector.close()

    async def fetch_token(self, data: dict, expected_response_model: Type[T]) -> T:
        """Fetch an access token from the server.

        :param data: The data to send to the server.

        :return: The token response.

        :raises OAuthError: If the token response cannot be fetched.
        """
        data["client_id"] = self.client_id
        if self.__client_secret is not None:
            data["client_secret"] = self.__client_secret

        try:
            async with self._connector:
                try:
                    response = await self._connector.call_api(
                        RequestMethod.POST,
                        self.endpoint("token"),
                        header_params={
                            "Accept": "application/json",
                            "Content-Type": "application/x-www-form-urlencoded",
                        },
                        post_params=data,
                        response_types_map={"200": expected_response_model},
                    )
                except EvoAPIException as e:
                    error_json: dict = e.content
                    title = error_json.get("error", "Unexpected response from server")
                    detail = error_json.get("error_description", str(e))
                    raise OAuthError(f"{title}: {detail}")
                except ValidationError as e:
                    raise OAuthError("Invalid token response from server.") from e
            return response
        except OAuthError:
            raise  # Re-raise OAuthError exceptions.
        except Exception as exc:  # noqa: E722
            # Catch any other exceptions and raise OAuthError.
            raise OAuthError("Unable to fetch access token." + str(exc)) from exc
