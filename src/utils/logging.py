"""
Structured JSON Logging Module for CloudGuard FinOps.
Configures structlog to output machine-parseable JSON logs for Datadog, ELK, and Grafana Loki.
"""
import os
import sys
import logging
import structlog


def setup_logging(level: str = "INFO", json_format: bool = True) -> None:
    """
    Configures standard library logging and structlog.
    In production (json_format=True), formats all log lines as single-line JSON strings.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if json_format or os.getenv("LOG_FORMAT") == "json":
        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processor=structlog.processors.JSONRenderer(),
        )
    else:
        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processor=structlog.dev.ConsoleRenderer(colors=True),
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "cloudguard") -> structlog.stdlib.BoundLogger:
    """Returns a structured logger bound with the specified module name."""
    return structlog.get_logger(name)
