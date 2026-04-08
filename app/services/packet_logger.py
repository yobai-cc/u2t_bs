from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.packet_log import PacketLog
from app.utils.codec import bytes_to_hex, decode_text


class PacketLogger:
    """Persists protocol traffic for page rendering and file inspection."""

    def __init__(self) -> None:
        settings = get_settings()
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("u2t.packet")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        if not self.logger.handlers:
            handler = RotatingFileHandler(settings.packet_log_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
            self.logger.addHandler(handler)

    def log_packet(
        self,
        *,
        db: Session,
        service_type: str,
        protocol: str,
        direction: str,
        src_ip: str,
        src_port: int,
        dst_ip: str,
        dst_port: int,
        payload: bytes,
    ) -> None:
        data_hex = bytes_to_hex(payload)
        data_text = decode_text(payload)
        db.add(
            PacketLog(
                service_type=service_type,
                protocol=protocol,
                direction=direction,
                src_ip=src_ip,
                src_port=src_port,
                dst_ip=dst_ip,
                dst_port=dst_port,
                data_hex=data_hex,
                data_text=data_text,
                length=len(payload),
            )
        )
        db.commit()
        self.logger.info("%s %s:%s -> %s:%s len=%s hex=%s", direction, src_ip, src_port, dst_ip, dst_port, len(payload), data_hex)


packet_logger = PacketLogger()
