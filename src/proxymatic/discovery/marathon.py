import logging
import socket
import json
import threading
import traceback
from cachetools import lru_cache
from urlparse import urlparse
from proxymatic.services import Server, Service
from proxymatic import util

@lru_cache(maxsize=1024)
def getAppVersion(socketpath, appid, version):
    path = '/v2/apps/%s/versions/%s' % (appid.strip('/'), version)
    response = util.unixrequest('GET', socketpath, path, None, {'Accept': 'application/json'})
    return json.loads(response)

class MarathonService(object):
    def __init__(self):
        self.priority = 100

class MarathonDiscovery(object):
    def __init__(self, backend, urls, interval, groupsize=1):
        self._backend = backend
        self._urls = [url.rstrip('/') for url in urls]
        self._socketpath = '/tmp/marathon.sock'
        self._interval = interval
        self._groupsize = groupsize
        self._healthy = False
        self._marathonService = MarathonService()
        self.priority = 10

        # Signal to perform a refresh. This avoid performing multiple refreshes
        # when many events are received in quick succession.
        self._condition = threading.Condition()
        self._dorefresh = False

        # Ensure the HAproxy load balancer is configured to proxy to the Marathon replicas
        self._connect()

    def isHealthy(self):
        return self._healthy

    def start(self):
        marathon = self

        # Trigger the refresh and release the refresh thread
        def triggerRefresh():
            marathon._condition.acquire()
            marathon._dorefresh = True
            marathon._condition.notify()
            marathon._condition.release()

        # Consume the Marathon event stream
        def eventstream():
            # Initiate the request which will push server sent events
            response = util.unixresponse('GET', self._socketpath, '/v2/events', None, {'Accept': 'text/event-stream'})
            if response.status < 200 or response.status >= 300:
                raise ValueError(response.read())

            # Consume server sent events one per line
            logging.info("Subscribed to Marathon event stream")
            while True:
                data = response.fp.readline()
                if data == "":
                    raise ValueError("Marathon event stream closed")

                # Events affecting state copied from https://github.com/mesosphere/marathon-lb/blob/master/marathon_lb.py
                if data.startswith('event:'):
                    if ('health_status_changed_event' in data or
                            'status_update_event' in data or
                            'api_post_event' in data):
                        logging.info('Triggering refresh based on Marathon %s', data.strip())
                        triggerRefresh()
                    else:
                        logging.debug('Ignoring Marathon %s', data.strip())

        util.run(eventstream, "Error subscribing to Marathon event stream '" + str(self._urls) + "': %s", graceperiod=60)

        # Run refresh() in thread with retry on error
        def refreshWorker():
            with marathon._condition:
                # Check if refresh should be triggered immediately
                marathon._condition.acquire()
                if not marathon._dorefresh:
                    # Wait for the trigger, but perform a refresh anyway when the wait expires
                    marathon._condition.wait(util.jitter(marathon._interval))

                # Reset the trigger
                marathon._dorefresh = False
                marathon._condition.release()

                # Perform the refresh
                marathon._refresh()

        util.run(refreshWorker, "Marathon error from '" + str(self._urls) + "/v2/tasks': %s", graceperiod=60)

    def _connect(self):
        # Start the local load balancer in front of Marathon
        service = Service(
            'marathon', 'marathon:%s' % self._urls, self._socketpath, 'unix',
            'http', healthcheck=True, healthcheckurl='/ping')

        for url in self._urls:
            parsed = urlparse(url)

            # Resolve hostnames since HAproxy wants IP addresses
            ipaddr = socket.gethostbyname(parsed.hostname or '127.0.0.1')
            server = Server(ipaddr, parsed.port or 80, parsed.hostname)
            service._add(server)

        self._backend.update(self._marathonService, {self._socketpath: service})

    def _refresh(self):
        # Poll Marathon for running tasks
        logging.debug("GET Marathon services from %s", self._socketpath)
        response = util.unixrequest('GET', self._socketpath, '/v2/tasks', None, {'Accept': 'application/json'})
        self._backend.update(self, self._parse(response))
        logging.debug("Refreshed services from Marathon at %s", self._urls)

        # Signal that we're up and running
        self._healthy = True

    def _applyServicePortOverrides(self, taskConfig, servicePorts):
        ports = list(servicePorts)

        for portIndex in range(len(ports)):
            overrideKey = 'com.meltwater.proxymatic.port.%d.servicePort' % portIndex
            overridePort = util.rget(taskConfig, 'labels', overrideKey)
            if overridePort is not None:
                if str(overridePort).isdigit():
                    ports[portIndex] = int(overridePort)
                else:
                    logging.warn("Port override %s for task %s is not numeric ", overrideKey, taskConfig.get('id'))

        return ports

    def _applyBackendAttributeInt(self, attribute, taskConfig, portIndex, server, divisor=1):
        attribKey = 'com.meltwater.proxymatic.port.%d.%s' % (portIndex, attribute)
        attribValue = util.rget(taskConfig, 'labels', attribKey)
        if attribValue is not None:
            if str(attribValue).isdigit():
                setattr(server, attribute, int(attribValue) / divisor)
            else:
                logging.warn("Weight %s=%s for task %s is not numeric ", attribKey, attribValue, taskConfig.get('id'))

    def _applyBackendConnectionTimeout(self, attribute, taskConfig, portIndex, server):
        attribKey = 'com.meltwater.proxymatic.service.%s' % (attribute)
        attribValue = util.rget(taskConfig, 'labels', attribKey)
        if attribValue is not None:
            if str(attribValue).isdigit():
                setattr(server, attribute, int(attribValue))
            else:
                logging.warn("Timeout %s=%s for task %s is not numeric ", attribKey, attribValue, taskConfig.get('id'))

    def _applyLoadBalancerMode(self, taskConfig, portIndex, service):
        modeKey = 'com.meltwater.proxymatic.port.%d.mode' % portIndex
        mode = util.rget(taskConfig, 'labels', modeKey)
        if mode is not None:
            if mode in ('tcp', 'http'):
                service.application = mode
            else:
                logging.warn("Load balancer connection mode %s=%s for task %s is not in [tcp, http]", modeKey, mode, taskConfig.get('id'))

    def _parse(self, content):
        services = {}

        try:
            # logging.debug(content)
            document = json.loads(content)
        except ValueError as e:
            raise RuntimeError("Failed to parse HTTP JSON response from Marathon (%s): %s" % (str(e), str(content)[0:150]))

        def failed(check):
            alive = check.get('alive', False)
            if not alive:
                cause = check.get('lastFailureCause', '')
                if cause:
                    logging.info("Task %s is failing health check with result '%s'", check.get('taskId', ''), cause)
                else:
                    logging.debug("Skipping task %s which is not alive (yet)", check.get('taskId', ''))
            return not alive

        for task in document.get('tasks', []):
            # Fetch exact config for this app version
            taskConfig = getAppVersion(self._socketpath, task.get('appId'), task.get('version'))

            exposedPorts = task.get('ports', [])
            servicePorts = task.get('servicePorts', [])
            seenServicePorts = set()

            # Apply servicePort overrides
            servicePorts = self._applyServicePortOverrides(taskConfig, servicePorts)

            # Skip tasks that are being killed
            if task.get('state') == 'TASK_KILLING':
                logging.debug("Skipping task %s as it's currently being killed", task.get('id'))
                continue

            for servicePort, portIndex in zip(servicePorts, range(len(servicePorts))):
                protocol = 'tcp'
                key = '%s/%s' % (servicePort, protocol.lower())

                # Marathon has been observed to sometimes return servicePort=0 failure cases
                if str(servicePort) == '0':
                    logging.warn("Skipping task with servicePort=0")
                    continue

                # Marathon returns multiple entries for services that expose both TCP and UDP using the same
                # port number. There's no way to separate TCP and UDP service ports at the moment.
                if servicePort in seenServicePorts:
                    continue
                seenServicePorts.add(servicePort)

                # Verify that all health checks pass
                healthChecks = taskConfig.get('healthChecks', [])
                healthResults = task.get('healthCheckResults', [])

                # Skip any task that isn't alive according to its health checks
                if any(failed(check) for check in healthResults):
                    continue

                # Skip tasks that hasn't yet responded to at least one of their health checks. Note that Marathon
                # considers tasks ready as soon as they respond OK to one of their defined health checks.
                if len(healthChecks) > 0 and len(healthResults) == 0:
                    logging.debug("Skipping task %s which hasn't responded to health checks yet", task.get('id', ''))
                    continue

                try:
                    exposedPort = exposedPorts[portIndex]

                    # Resolve hostnames since HAproxy wants IP addresses
                    ipaddr = socket.gethostbyname(task['host'])
                    server = Server(ipaddr, exposedPort, task['host'])

                    # Set backend load balancer options
                    self._applyBackendAttributeInt('weight', taskConfig, portIndex, server)
                    self._applyBackendAttributeInt('maxconn', taskConfig, portIndex, server, self._groupsize)
                    self._applyBackendConnectionTimeout('timeoutclient', taskConfig, portIndex, server)
                    self._applyBackendConnectionTimeout('timeoutserver', taskConfig, portIndex, server)

                    # Append backend to service
                    if key not in services:
                        name = '.'.join(reversed(filter(bool, task['appId'].split('/'))))
                        services[key] = Service(name, 'marathon:%s' % self._urls, servicePort, protocol)
                    services[key]._add(server)

                    # Set load balancer protocol mode
                    self._applyLoadBalancerMode(taskConfig, portIndex, services[key])

                except Exception as e:
                    logging.warn("Failed parse service %s backend %s: %s", task.get('appId', ''), task.get('id', ''), str(e))
                    logging.debug(traceback.format_exc())

        return services
