from app.services.udp_server import UDPRelayConfig, UDPRelayService


def test_update_config_changes_runtime_state() -> None:
    service = UDPRelayService()
    config = UDPRelayConfig(
        bind_ip="0.0.0.0",
        bind_port=9000,
        cloud_ip="1.2.3.4",
        cloud_port=9001,
        custom_reply_data="aa55",
        hex_mode=True,
    )

    service.update_config(config)

    assert service.config.bind_ip == "0.0.0.0"
    assert service.config.bind_port == 9000
    assert service.config.cloud_ip == "1.2.3.4"
    assert service.config.cloud_port == 9001
    assert service.config.custom_reply_data == "aa55"
    assert service.config.hex_mode is True


def test_track_client_addr_stores_latest_non_cloud_peer() -> None:
    service = UDPRelayService()
    service.update_config(
        UDPRelayConfig(
            bind_ip="0.0.0.0",
            bind_port=9000,
            cloud_ip="10.0.0.8",
            cloud_port=9001,
            custom_reply_data="reply",
            hex_mode=False,
        )
    )

    service.record_client_addr(("127.0.0.1", 50123))

    assert service.last_client_addr == ("127.0.0.1", 50123)
