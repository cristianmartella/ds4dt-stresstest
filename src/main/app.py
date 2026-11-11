import logging
import os
import json
import subprocess
import time
import random
import requests
import multiprocessing as mp
import queue
from flask import Flask, request
from opentelemetry import trace, metrics, context
from opentelemetry.trace import SpanContext, TraceFlags, set_span_in_context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, BatchSpanProcessor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from init import (
    conf_devices,
    conf_services,
    wait_iotagent
)

### Environment variables
port = int(os.getenv('PORT', '8000'))
device_id = os.getenv("DEVICE_ID", "DEVICE00")

init_services = os.getenv("INIT_SERVICES", "true").lower() == "true"
init_devices = os.getenv("INIT_DEVICES", "true").lower() == "true"
dsc_enabled = os.getenv("DSC_ENABLED", "false").lower() == "true"
cb_healthcheck_enabled = os.getenv("CB_HEALTHCHECK_ENABLED", "false").lower() == "true"

apikeys = {
    "APIKEY_AQ": os.getenv("APIKEY_AQ", "IGNORE"),
    "APIKEY_ENERGY": os.getenv("APIKEY_ENERGY", "IGNORE"),
    "APIKEY_DEVICE": os.getenv("APIKEY_DEVICE", "IGNORE"),
    "APIKEY_POSE": os.getenv("APIKEY_POSE", "IGNORE"),
    "APIKEY_CMD": os.getenv("APIKEY_CMD", "IGNORE")
}

conf_files = {
    "device_conf": os.getenv("CONF_FILE_PATH_DEVICE", "resources/device_conf.docker.json"),
    "service_group_conf": os.getenv("CONF_FILE_PATH_SERVICE_GROUP", "resources/service_group_conf.docker.json")
}

cbroker_url = os.getenv("CBROKER_URL", "http://localhost:1026")
cbroker_hc_url = os.getenv("CBROKER_HC_URL", f"{cbroker_url}/q/health")
mqtt_url = os.getenv("MQTT_URL", "mqtt://localhost:1883")
iotagent_url_n = os.getenv("IOTAGENT_URL_N", "http://localhost:4041")
iotagent_url_s = os.getenv("IOTAGENT_URL_S", "http://localhost:7896")

headers_iota = {
    "Content-Type": "application/json",
    "fiware-service": os.getenv("FIWARE_SERVICE", "openiot"),
    "fiware-servicepath": os.getenv("FIWARE_SERVICE_PATH", "/")
}

headers_cb = {
    "Accept": "application/ld+json",
    "Link": '<https://raw.githubusercontent.com/smart-data-models/dataModel.Device/refs/heads/master/context.jsonld>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"',
    "NGSILD-Tenant": "openiot",
    "NGSILD-Path": "/"
}

access_token = ""
access_token_refresh_interval = 1800  # 30 minutes
access_token_path = "resources/.access_token.tmp"



# Configure logging with OpenTelemetry
class OpenTelemetryLogFormatter(logging.Formatter):
    def format(self, record):
        # Add trace and span context to log record
        current_span = trace.get_current_span()
        if current_span:
            span_context = current_span.get_span_context()
            if span_context and span_context.is_valid:
                record.trace_id = f"{span_context.trace_id:032x}"
                record.span_id = f"{span_context.span_id:016x}"
            else:
                record.trace_id = "00000000000000000000000000000000"
                record.span_id = "0000000000000000"
        else:
            record.trace_id = "00000000000000000000000000000000"
            record.span_id = "0000000000000000"
        return super().format(record)

# Create formatter
formatter = OpenTelemetryLogFormatter(
    '%(asctime)s - %(name)s - %(levelname)s - trace_id=%(trace_id)s span_id=%(span_id)s - %(message)s'
)

# Set up root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
root_logger.addHandler(handler)


# Create Flask app
app = Flask(__name__)


# Disable Werkzeug's default logger
app.logger.handlers = []
werkzeug_logger = logging.getLogger('werkzeug')
werkzeug_logger.disabled = True

# Create a custom logger for HTTP access
http_logger = logging.getLogger('http.access')
http_logger.setLevel(logging.INFO)
http_logger.addHandler(handler)

# # Set up multiprocessing logging
# mp_logger = logging.getLogger("multiprocessing_logger")
# mp_logger.setLevel(logging.INFO)
# mp_logger.addHandler(handler)




# Before request handler to update metrics
@app.before_request
def before_request():
    request.start_time = time.time()

# After request handler to update metrics
@app.after_request
def after_request(response):
    duration_ms = (time.time() - request.start_time) * 1000

    # Log the request with the current trace context
    http_logger.info(
        '%s - - [%s] "%s %s %s" %s %s (%.2fms)',
        request.remote_addr,
        time.strftime('%d/%b/%Y %H:%M:%S'),
        request.method,
        request.path,
        request.environ.get('SERVER_PROTOCOL', ''),
        response.status_code,
        response.content_length or '-',
        duration_ms
    )
    return response




# Instrument Flask for traces and logs
FlaskInstrumentor().instrument_app(app)
LoggingInstrumentor().instrument()

# Custom metric
meter = metrics.get_meter(__name__)
task_counter = meter.create_counter(
    "task_requests", 
    description="Number of task requests"
)
cb_health_gauge = meter.create_up_down_counter(
    name="cb_health_status",
    description="Health status of the Context Broker",
    unit="status",
)

# Tracer for custom spans
tracer = trace.get_tracer(__name__)

worker_provider = TracerProvider()
worker_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(worker_provider)


@app.route('/')
def home():
    logging.info("Home endpoint accessed")
    return "Welcome to the Flask App!", 200


@app.route('/task')
def task():
    with tracer.start_as_current_span("process-task") as span:
        task_counter.add(1)
        logging.info("Task endpoint accessed")
        return "Task completed!", 200


@app.route('/refresh-token', methods=['POST'])
def refresh_token():
    with tracer.start_as_current_span("manual-refresh-token") as span:
        logging.info("Manual token refresh triggered via endpoint.")
        jwt_token_refresh()
        return "Token refresh triggered.", 200



# Endpoint to start load generation
@app.route('/start', methods=['POST'])
def start():
    apikey = apikeys["APIKEY_AQ"]
    params = request.json
    delta_t = params.get("delta_t", 10)
    burst_size = params.get("burst_size", 10)
    iterations = params.get("iterations", 5)
    mode = params.get("mode", "fixed") # fixed or random burst size (using uniform distribution)
    entity_type = "AirQualityObserved"

    span = trace.get_current_span()
    span.set_attribute("load_test.delta_t", delta_t)
    span.set_attribute("load_test.burst_size", burst_size)
    span.set_attribute("load_test.iterations", iterations)
    span.set_attribute("load_test.mode", mode)

    for ii in range(0, iterations):
        with tracer.start_as_current_span(f"iteration-{ii+1}") as iter_span:
            context_dict = serialize_current_span_context()

            logging.info(f"Starting load generation with delta_t={delta_t}, burst_size={burst_size}, iteration={ii+1}/{iterations}...")
            logging.info(f"Number of CPU: {mp.cpu_count()}")
            post_jobs = []
            get_jobs = []
            
            mode=params.get("mode", "fixed").lower()
            post_jobs_count=random.randint(round(burst_size/2), burst_size) if mode=="random" else burst_size
            get_jobs_count=random.randint(round(burst_size/3), post_jobs_count) if mode=="random" else burst_size

            # post_requests_total.labels(status=f"iteration {ii}", endpoint=f"/iot/json?k={apikey}&i={device_id}").inc(post_jobs_count)
            # get_requests_total.labels(status=f"iteration {ii}", endpoint=f"/ngsi-ld/v1/entities?type={entity_type}").inc(get_jobs_count)

            logging.info(f"Sending burst of {post_jobs_count} post requests and {get_jobs_count} get requests...")
            for _ in range(post_jobs_count):
                random.seed(random.randint(0,10000))
                payload = {
                    "temperature": f"{round(random.uniform(10,30), 2)}",
                    "relativeHumidity": f"{round(random.uniform(50,90), 2)}",
                    "atmosphericPressure": f"{round(random.uniform(990,1020), 2)}"
                }
                job = mp.Process(target=send_test_data, args=(apikey, device_id, payload, context_dict,))
                post_jobs.append(job)
                job.start()
            
            for _ in range(get_jobs_count):
                job = mp.Process(target=get_test_data, args=(entity_type, context_dict,))
                get_jobs.append(job)
                job.start()

            for jj in range(0, post_jobs_count):
                post_jobs[jj].join()

                if jj<get_jobs_count:
                    get_jobs[jj].join()

                time.sleep(1)  # slight delay to avoid all processes finishing at the exact same time

        post_jobs.clear()
        get_jobs.clear()
        time.sleep(delta_t)

    return ["Load generation completed."], 200



def serialize_current_span_context():
    """
    Serializes the current span context for passing to another process.
    Returns a dictionary that can be pickled and sent across process boundaries.
    """
    current_span = trace.get_current_span()
    span_ctx = current_span.get_span_context()

    if not span_ctx.is_valid:
        return None

    return {
        "trace_id": span_ctx.trace_id,
        "span_id": span_ctx.span_id,
        "trace_flags": int(span_ctx.trace_flags),
        "trace_state": str(span_ctx.trace_state) if span_ctx.trace_state else None
    }

def deserialize_span_context(context_dict):
    """
    Deserializes a span context received from another process.
    Returns a SpanContext object or None if deserialization fails.
    """
    if not context_dict:
        return None

    try:
        return SpanContext(
            trace_id=context_dict["trace_id"],
            span_id=context_dict["span_id"],
            is_remote=True,
            trace_flags=TraceFlags(context_dict["trace_flags"]),
            trace_state=None  # Simplified for this example
        )
    except (KeyError, ValueError):
        return None


# Function to periodically issue a valid JWT token
def jwt_token_refresh():
    # Set up multiprocessing logging
    mp_logger = logging.getLogger("multiprocessing_logger_jwt_token_refresh")
    mp_logger.setLevel(logging.INFO)
    mp_logger.addHandler(handler)

    credential_type = os.getenv("CREDENTIAL_TYPE", "UserCredential")
    if os.path.exists("resources/credentials.json"):
        verifiable_credential = json.load(open("resources/credentials.json")).get(os.getenv("CREDENTIAL_TYPE", "UserCredential"), None)

    while True:
        with tracer.start_as_current_span("jwt-token-refresh") as span:
            mp_logger.info("Refreshing JWT token...")
            access_token = subprocess.run([f"./scripts/get_access_token_oid4vp.sh", cbroker_url, verifiable_credential, credential_type, "resources/wallet-identity"], capture_output=True, text=True).stdout.strip()

            with open(access_token_path, "w") as f:
                f.write(access_token)
            mp_logger.info(f"JWT token refreshed successfully.")

        time.sleep(access_token_refresh_interval)  # Sleep for the specified interval


# Function to periodically check Context Broker health and update gauge
def cb_healthcheck():
    # Set up multiprocessing logging
    mp_logger = logging.getLogger("multiprocessing_logger_cb_healthcheck")
    mp_logger.setLevel(logging.INFO)
    mp_logger.addHandler(handler)

    # Each process needs its own tracer provider
    # Note: In production, configure this to export to the same backend
    worker_tracer = trace.get_tracer(__name__)

    status = 0
    while True:

        with worker_tracer.start_as_current_span("cb-healthcheck") as span:
            time.sleep(10)
            try:
                response = requests.get(
                    url=f"{cbroker_hc_url}",
                    timeout=5
                )
                mp_logger.info(f"CB healthcheck response on {cbroker_hc_url}: {response.status_code}")
            except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                mp_logger.error(f"Error connecting to CB at {cbroker_hc_url}: {e}")
                response = None
            finally:
                if response and response.status_code == 200:
                    cb_health_gauge.add(1)
                    status = status+1
                    while status > 1:
                        cb_health_gauge.add(-1)
                        status = status-1
                elif status > 0:
                    cb_health_gauge.add(-1)
                    status = status-1

                span.set_attribute("cb.up", status)
                mp_logger.info(f"CB health status: {status}")
    
    mp_logger.info("CB healthcheck process exiting.")
    mp_logger.info("Shutting down tracer provider for CB healthcheck process.")
    # worker_provider.shutdown()


# Function to send test data to IoT Agent and record duration in summary
def send_test_data(apikey,deviceid,payload,context_dict) -> float:
    # Set up multiprocessing logging
    mp_logger = logging.getLogger(f"multiprocessing_logger_{mp.current_process().name}")
    mp_logger.setLevel(logging.INFO)
    mp_logger.addHandler(handler)

    # update headers with new token
    access_token = ""
    if os.path.exists(access_token_path):
        with open(access_token_path, "r") as f:
            access_token = f.read().strip()
            headers_iota["Authorization"] = f"Bearer {access_token}"
            mp_logger.info(f"iota headers -> {headers_iota}")


    # worker_tracer = trace.get_tracer(__name__)

    # # Reconstruct the parent span context
    # parent_context = deserialize_span_context(context_dict)

    # # Create a non-recording span with the parent context
    # parent_span = trace.NonRecordingSpan(parent_context)
    # ctx = set_span_in_context(parent_span)
    # token = context.attach(ctx)

    # try:
    #     with worker_tracer.start_as_current_span("post-test-data") as span:
    #         span.set_attribute("device.id", deviceid)
    #         span.set_attribute("payload.temperature", payload["temperature"])
    #         span.set_attribute("payload.relativeHumidity", payload["relativeHumidity"])
    #         span.set_attribute("payload.atmosphericPressure", payload["atmosphericPressure"])

    iotagent_url_http = f"{iotagent_url_s}/iot/d?k={apikey}&i={deviceid}"
    try:
        response = requests.post(
            url=iotagent_url_http,
            headers=headers_iota,
            json=payload
        )
        mp_logger.info(f"Response from IoT Agent: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        mp_logger.error(f"Error connecting to IoT Agent at {iotagent_url_http}: {e}")
        response = None
    # finally:
    #     context.detach(token)
    # worker_provider.shutdown()


# Function to get test data from Context Broker and record duration in summary
def get_test_data(entity_type, context_dict):
    # Set up multiprocessing logging
    mp_logger = logging.getLogger(f"multiprocessing_logger_{mp.current_process().name}")
    mp_logger.setLevel(logging.INFO)
    mp_logger.addHandler(handler)

    # update headers with new token
    access_token = ""
    if os.path.exists(access_token_path):
        with open(access_token_path, "r") as f:
            access_token = f.read().strip()
            headers_cb["Authorization"] = f"Bearer {access_token}"
            mp_logger.info(f"cb headers -> {headers_cb}")

    # worker_tracer = trace.get_tracer(__name__)

    # # Reconstruct the parent span context
    # parent_context = deserialize_span_context(context_dict)

    # # Create a non-recording span with the parent context
    # parent_span = trace.NonRecordingSpan(parent_context)
    # ctx = set_span_in_context(parent_span)
    # token = context.attach(ctx)

    # try:
    #     with worker_tracer.start_as_current_span("get-test-data") as span:
    cbroker = f"{cbroker_url}/ngsi-ld/v1/entities?type={entity_type}"
    try:
        response = requests.get(
            url=cbroker,
            headers=headers_cb
        )
        mp_logger.info(f"Response from CB: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        mp_logger.error(f"Error connecting to CB at {cbroker}: {e}")
        response = None
    # finally:
    #     context.detach(token)
    # worker_provider.shutdown()



# Function to start the flask server
def start_server():
    # Set up multiprocessing logging
    mp_logger = logging.getLogger(f"multiprocessing_logger_flask_server")
    mp_logger.setLevel(logging.INFO)
    mp_logger.addHandler(handler)

    try:
        mp_logger.info(f'Starting server on port {port}...')
        app.run(host='0.0.0.0', port=port)
    except Exception as e:
        mp_logger.error(f'Server failed to start: {e}')
        exit(1)



if __name__ == "__main__":
    # Set up multiprocessing logging
    mp.log_to_stderr(logging.INFO)

    if cb_healthcheck_enabled:
        logging.info("Starting healthcheck process for Context Broker...")
        healthcheck_job = mp.Process(target=cb_healthcheck, args=())
        healthcheck_job.start()
        logging.info("Healthcheck process for Context Broker started.")

    if dsc_enabled:
        logging.info("Starting JWT token refresh process...")
        token_refresh_job = mp.Process(target=jwt_token_refresh, args=())
        token_refresh_job.start()
        logging.info("JWT token refresh process started.")


    if wait_iotagent(iotagent_url_n, logging, tracer) == 200:
        if init_services:
            logging.info("configuring service group...")
            conf_services(apikeys, cbroker_url, conf_files["service_group_conf"], logging, tracer)

        if init_devices:
            logging.info("configuring device group...")
            conf_devices(device_id, apikeys, conf_files["device_conf"], logging, tracer)

    logging.info("IoT Agent initialized.")


    logging.info("Starting Flask server process...")
    server_job = mp.Process(target=start_server, args=())
    server_job.start()
    logging.info("Flask server process started.")

    server_job.join()
    worker_provider.shutdown()
