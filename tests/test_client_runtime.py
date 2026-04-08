import asyncio

import pytest

from app.services.client_runtime import ClientRuntimeConfig, ClientRuntimeService


def test_update_config_changes_snapshot_values() -> None:
    service = ClientRuntimeService()
    service.update_config(ClientRuntimeConfig(protocol="TCP", target_ip="127.0.0.1", target_port=9200, hex_mode=True))

    snapshot = service.snapshot()

    assert snapshot["protocol"] == "TCP"
    assert snapshot["target_ip"] == "127.0.0.1"
    assert snapshot["target_port"] == 9200
    assert snapshot["hex_mode"] is True
    assert snapshot["connected"] is False


@pytest.mark.anyio
async def test_disconnect_when_idle_is_safe() -> None:
    service = ClientRuntimeService()
    await service.disconnect()
    assert service.snapshot()["connected"] is False


@pytest.mark.anyio
async def test_tcp_mode_connect_send_receive_and_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[bytes] = []
    packets: list[dict[str, object]] = []
    logs: list[tuple[str, str, str, str]] = []

    monkeypatch.setattr(
        "app.services.client_runtime.packet_logger.log_packet",
        lambda **kwargs: packets.append(kwargs),
    )
    monkeypatch.setattr(
        "app.services.client_runtime.system_log_service.log_to_db",
        lambda level, category, message, detail="", db=None: logs.append((level, category, message, detail)),
    )

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        data = await reader.read(4096)
        received.append(data)
        writer.write(b"reply")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    sockname = server.sockets[0].getsockname()

    service = ClientRuntimeService()
    service.update_config(ClientRuntimeConfig(protocol="TCP", target_ip="127.0.0.1", target_port=sockname[1], hex_mode=False))

    await service.connect()
    await service.send_manual("hello")

    for _ in range(20):
        if service.snapshot()["rx_count"] == 5:
            break
        await asyncio.sleep(0.01)

    assert received == [b"hello"]
    assert service.snapshot()["tx_count"] == 5
    assert service.snapshot()["rx_count"] == 5
    assert packets[-1]["direction"] == "remote -> client"
    assert packets[-1]["payload"] == b"reply"
    assert any("Client connected" in message for _, _, message, _ in logs)

    await service.disconnect()
    assert service.snapshot()["connected"] is False

    server.close()
    await server.wait_closed()


@pytest.mark.anyio
async def test_udp_mode_connect_send_receive_and_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[bytes] = []
    packets: list[dict[str, object]] = []

    monkeypatch.setattr(
        "app.services.client_runtime.packet_logger.log_packet",
        lambda **kwargs: packets.append(kwargs),
    )
    monkeypatch.setattr(
        "app.services.client_runtime.system_log_service.log_to_db",
        lambda *args, **kwargs: None,
    )

    responder_transport: asyncio.DatagramTransport | None = None
    reply_sent = asyncio.Event()

    class Responder(asyncio.DatagramProtocol):
        def connection_made(self, transport: asyncio.BaseTransport) -> None:
            nonlocal responder_transport
            responder_transport = transport  # type: ignore[assignment]

        def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
            received.append(data)
            assert responder_transport is not None
            responder_transport.sendto(b"pong", addr)
            reply_sent.set()

    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(lambda: Responder(), local_addr=("127.0.0.1", 0))
    sockname = transport.get_extra_info("sockname")

    service = ClientRuntimeService()
    service.update_config(ClientRuntimeConfig(protocol="UDP", target_ip="127.0.0.1", target_port=sockname[1], hex_mode=False))

    await service.connect()
    await service.send_manual("ping")
    await asyncio.wait_for(reply_sent.wait(), timeout=1)

    for _ in range(20):
        if service.snapshot()["rx_count"] == 4:
            break
        await asyncio.sleep(0.01)

    assert received == [b"ping"]
    assert service.snapshot()["tx_count"] == 4
    assert service.snapshot()["rx_count"] == 4
    assert packets[0]["direction"] == "client -> remote"
    assert packets[-1]["direction"] == "remote -> client"

    await service.disconnect()
    assert service.snapshot()["connected"] is False

    transport.close()
