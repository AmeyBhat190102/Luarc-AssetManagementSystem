import logging
import structlog


def setup_logging(log_level: str = "DEBUG") -> None:
    """
    Configure structlog for pretty, coloured console output during development.

    Each log line includes:
      - timestamp
      - log level
      - logger name  (module that emitted the log)
      - event message
      - any extra key=value context bound at call-site
    """
    level = getattr(logging, log_level.upper(), logging.DEBUG)

    # Route stdlib logging through structlog's ProcessorFormatter
    # so uvicorn/fastapi logs also get the same pretty format.
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.ExceptionRenderer(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            # Prepare event dict for stdlib if it ends up there,
            # otherwise render directly.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
