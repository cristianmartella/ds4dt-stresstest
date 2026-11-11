import os
import json
from time import sleep
import time
import requests


### Environment variables
iotagent_url_n = os.getenv("IOTAGENT_URL_N", "http://localhost:4041")
headers = {
    "Content-Type": "application/json",
    "fiware-service": os.getenv("FIWARE_SERVICE", "openiot"),
    "fiware-servicepath": os.getenv("FIWARE_SERVICE_PATH", "/")
}



###
### Configure devices in IoT Agent
###
def conf_devices(device_id, apikeys, conf_file, logging, tracer) -> int:
    with tracer.start_as_current_span("conf_devices") as span:
        with open(conf_file) as f:
            device_conf = json.load(f)
            for device in device_conf["devices"]:
                device["device_id"] = device_id
                device["apikey"] = apikeys.get(device["apikey"], "IGNORE")

                attributes = device.get("attributes", [])
                for attr in attributes:
                    if "entity_name" in attr and "DEVICE_ID" in attr["entity_name"]:
                        attr["entity_name"] = attr["entity_name"].replace("DEVICE_ID", device_id)
                
        # request to iot-agent to register the device group
        logging.info(f"Registering device {device_id} to IoT Agent at {iotagent_url_n}...")
        try:
            response = requests.post(
                f"{iotagent_url_n}/iot/devices",
                headers=headers,
                json=device_conf
            )
        except requests.exceptions.RequestException as e:
            logging.error(f"Error connecting to IoT Agent at {iotagent_url_n}: {e}")

        if response.status_code in [200, 201]:
            logging.info(f"Device group {device_id} registered successfully.")
        elif response.status_code == 409:
            logging.warning(f"Device group {device_id} already exists.")
        else:
            logging.warning(f"Failed to register device group {device_id}. Status code: {response.status_code}, Response: {response.text}")

        return response.status_code


###
### Configure services in IoT Agent
###
def conf_services(apikeys, cbroker_url, conf_file, logging, tracer) -> int:
    with tracer.start_as_current_span("conf_services") as span:
        with open(conf_file) as f:
            service_group_conf = json.load(f)
            for service in service_group_conf["services"]:
                if service["apikey"] in apikeys:
                    service["apikey"] = apikeys[service["apikey"]]

                service["cbroker"] = cbroker_url

        # request to iot-agent to register the service group
        logging.info(f"Registering service group to IoT Agent at {iotagent_url_n}...")
        try:
            response = requests.post(
                f"{iotagent_url_n}/iot/services",
                headers=headers,
                json=service_group_conf
            )
            status_code = response.status_code
        except requests.exceptions.RequestException as e:
            logging.error(f"conf_services -> Error connecting to IoT Agent at {iotagent_url_n}: {e}")
            status_code = 500

        if status_code in [200, 201]:
            logging.info("Service group registered successfully.")
        elif status_code == 409:
            logging.warning("Service group already exists.")
        else:
            logging.warning(f"Failed to register service group. Status code: {status_code}, Response: {response.text}")

        return status_code


###
### Check if IoT Agent is reachable
###
def wait_iotagent(iotagent_url_n, logging, tracer) -> int:
    with tracer.start_as_current_span("wait_iotagent") as span:
        logging.info(f"Checking connectivity to IoT Agent at {iotagent_url_n}...")

        while True:
            try:
                response = requests.get(
                    url=f"{iotagent_url_n}/iot/about",
                    headers=headers
                )
                logging.info(f"Response from IoT Agent: {response.status_code} - {response.text}")
            except requests.exceptions.RequestException as e:
                logging.error(f"wait_iotagent -> Error connecting to IoT Agent at {iotagent_url_n}: {e}")
                response = None
                sleep(5)  # wait before retrying
                continue

            if response and response.status_code == 200:
                logging.info("IoT Agent is up and running.")
                return response.status_code
            else:
                logging.error(f"wait_iotagent -> IoT Agent is not reachable at {iotagent_url_n}. Please check the service.")
                return response.status_code


###
### Retrieve service group list from IoT Agent
###
def get_service_group(iotagent_url_n, logging) -> list:
    logging.info(f"Getting service group info from IoT Agent at {iotagent_url_n}...")

    try:
        start_time = time.time()
        response = requests.get(
            url=f"{iotagent_url_n}/iot/services",
            headers=headers
        )
        logging.info(f"Response from IoT Agent: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"get_service_group -> Error connecting to IoT Agent at {iotagent_url_n}: {e}")
        response = None
    finally:
        # Record the request duration in the summary
        duration = time.time() - start_time
        posts_latency_summary.labels(method="GET", endpoint="/iot/services").observe(duration)

    if response and response.status_code == 200:
        logging.info("Service group info retrieved successfully.")
        return response.json().get("services", [])
    else:
        logging.error(f"get_service_group -> Failed to retrieve service group info from IoT Agent at {iotagent_url_n}. Please check the service.")
        return []


###
### Retrieve device group list from IoT Agent
###
def get_device_group(iotagent_url_n, logging) -> list:
    logging.info(f"Getting device group info from IoT Agent at {iotagent_url_n}...")

    try:
        start_time = time.time()
        response = requests.get(
            url=f"{iotagent_url_n}/iot/devices",
            headers=headers
        )
        logging.info(f"Response from IoT Agent: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        logging.error(f"get_device_group -> Error connecting to IoT Agent at {iotagent_url_n}: {e}")
        response = None
    finally:
        # Record the request duration in the summary
        duration = time.time() - start_time
        posts_latency_summary.labels(method="GET", endpoint="/iot/devices").observe(duration)

    if response and response.status_code == 200:
        logging.info("Device group info retrieved successfully.")
        return response.json().get("devices", [])
    else:
        logging.error(f"get_device_group -> Failed to retrieve device group info from IoT Agent at {iotagent_url_n}. Please check the service.")
        return []

