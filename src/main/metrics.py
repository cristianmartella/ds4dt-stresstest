import logging
import os
import shutil
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    CollectorRegistry,
    disable_created_metrics,
    multiprocess
)
from prometheus_summary import Summary


logging.info("Initializing Prometheus multiprocess directory...")
prometheus_stats = os.getenv("PROMETHEUS_MULTIPROC_DIR", "/tmp/prometheus")
if os.path.exists(prometheus_stats):
    shutil.rmtree(prometheus_stats)
os.mkdir(prometheus_stats)
logging.info(f"Prometheus multiprocess directory initialized at {prometheus_stats}.")

logging.info("Configuring Prometheus registries...")
disable_created_metrics()
registry = CollectorRegistry()
multiprocess.MultiProcessCollector(registry)
logging.info("Prometheus registries configured.")


# Counter metric for tracking HTTP requests
http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests received",
    ["status", "path", "method"],
    registry=registry,
)

# Gauge metric for tracking active HTTP requests
active_requests_gauge = Gauge(
    "http_active_requests",
    "Number of active connections to the service",
    registry=registry
)

# Histogram metric for request duration
latency_histogram = Histogram(
    "http_request_duration_seconds",
    "Duration of HTTP requests",
    ["status", "path", "method"],
    registry=registry,
)

# Summary metric for request duration
posts_latency_summary = Summary(
    "post_request_duration_seconds",
    "Duration of requests to iot-agent",
    ["method", "endpoint"],
    #invariants=((0.50, 0.05), (0.75, 0.02), (0.90, 0.01), (0.95, 0.005), (0.99, 0.001)),
    registry=registry,
)

# POST requests counter
post_requests_total = Counter(
    "post_requests_total",
    "Total number of POST requests sent to the IoT Agent",
    ["status", "endpoint"],
    registry=registry,
)

# GET requests counter
get_requests_total = Counter(
    "get_requests_total",
    "Total number of GET requests sent to the CB",
    ["status", "endpoint"],
    registry=registry,
)

# Health check metric
# https://prometheus.github.io/client_python/multiprocess/
service_health_cb_gauge = Gauge(
    "service_health_cb",
    "Health status of the CB service (1 = healthy, 0 = unhealthy)",
    registry=registry,
    multiprocess_mode='livemax'
)