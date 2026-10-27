"""Stand-ins for the connector and Harlequin's driver, for tests with no account."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Sequence, cast

from harlequin_snowflake.adapter import HarlequinSnowflakeConnection

if TYPE_CHECKING:
    from harlequin.driver import HarlequinDriver

Responder = Callable[[str, "Sequence[Any] | None"], "list[dict[str, Any]]"]


class FakeCursor:
    def __init__(self, server: FakeSnowflake) -> None:
        self.server = server
        self.rows: list[dict[str, Any]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> FakeCursor:
        self.server.calls.append((sql, None if params is None else list(params)))
        self.rows = self.server.respond(sql, params)
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class FakeSnowflake:
    """A `SnowflakeConnection` that records what it is sent."""

    def __init__(self, respond: Responder | None = None) -> None:
        self.calls: list[tuple[str, list[Any] | None]] = []
        self.respond: Responder = respond or (lambda sql, params: [])

    def cursor(self, *_: Any) -> FakeCursor:
        return FakeCursor(self)


def fake_connection(
    respond: Responder | None = None,
) -> tuple[HarlequinSnowflakeConnection, FakeSnowflake]:
    """A Harlequin connection over a `FakeSnowflake`, built without logging in."""
    server = FakeSnowflake(respond)
    connection = HarlequinSnowflakeConnection.__new__(HarlequinSnowflakeConnection)
    connection.conn = cast(Any, server)
    return connection, server


class FakeDriver:
    """A `HarlequinDriver` that records what an interaction asked of the app."""

    def __init__(self) -> None:
        self.buffers: list[str] = []
        self.inserted: list[str] = []
        self.notifications: list[tuple[str, str]] = []
        self.refreshed = False

    def insert_text_in_new_buffer(self, text: str) -> None:
        self.buffers.append(text)

    def insert_text_at_selection(self, text: str) -> None:
        self.inserted.append(text)

    def confirm_and_execute(
        self, callback: Callable[[], None], instructions: str = ""
    ) -> None:
        callback()

    def notify(self, message: str, severity: str = "information") -> None:
        self.notifications.append((message, severity))

    def refresh_catalog(self) -> None:
        self.refreshed = True

    def as_driver(self) -> HarlequinDriver:
        return cast("HarlequinDriver", self)
