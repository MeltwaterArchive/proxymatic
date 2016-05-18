import sys, logging, socket, time, json, threading
from cachetools import lru_cache
from urlparse import urlparse
from proxymatic.services import Server, Service
from proxymatic.util import *

@lru_cache(maxsize=1024)
def _getAppVersion(socketpath, appid, version):
    path = '/v2/apps/%s/versions/%s' % (appid.strip('/'), version)
    response = unixrequest('GET', socketpath, path, None, {'Accept': 'application/json'})
    return json.loads(response)

class MarathonService(object):
    def __init__(self):
        self.priority = 100

class MarathonDiscovery(object):
    def __init__(self, backend, urls, interval):
        self._backend = backend
        self._urls = [url.rstrip('/') for url in urls]
        self._socketpath = '/tmp/marathon.sock'
        self._interval = interval
        self._marathonService = MarathonService()
        self.priority = 10
        
        # Signal to perform a refresh. This avoid performing multiple refreshes
        # when many events are received in quick succession.
        self._condition = threading.Condition()
        self._dorefresh = False

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
            response = unixresponse('GET', self._socketpath, '/v2/events', None, {'Accept': 'text/event-stream'})
            if response.status < 200 or response.status >= 300:
                raise ValueError(response.read())

            # Consume server sent events one per line
            logging.info("Subscribed to Marathon event stream")
            while True:
                data = response.fp.readline()
                if data == "":
                    raise ValueError("Marathon event stream closed")
                
                # Events affecting state copied from https://github.com/mesosphere/marathon-lb/blob/master/marathon_lb.py
                if data.startswith('event:') and (
                        'health_status_changed_event' in data or 
                        'status_update_event' in data or 
                        'api_post_event' in data):
                    logging.info('Received %s', data)
                    triggerRefresh()

        run(eventstream, "Error subscribing to Marathon event stream '" + str(self._urls) + "': %s")

        # Run refresh() in thread with retry on error
        def refreshWorker():
            with marathon._condition:
                # Check if refresh should be triggered immediately
                marathon._condition.acquire()
                if not marathon._dorefresh:
                    # Wait for the trigger, but perform a refresh anyway when the wait expires
                    marathon._condition.wait(marathon._interval)
                
                # Reset the trigger
                marathon._dorefresh = False
                marathon._condition.release()
                
                # Perform the refresh
                marathon._refresh()
        
        run(refreshWorker, "Marathon error from '" + str(self._urls) + "/v2/tasks': %s")
        
    def _connect(self):
        # Start the local load balancer in front of Marathon
        service = Service(
            'marathon.local', 'marathon:%s' % self._urls, self._socketpath, 'unix', 
            'http', healthcheck=True, healthcheckurl='/ping')

        for url in self._urls:
            parsed = urlparse(url)

            # Resolve hostnames since HAproxy wants IP addresses
            ipaddr = socket.gethostbyname(parsed.hostname or '127.0.0.1')
            server = Server(ipaddr, parsed.port or 80)
            service._add(server)

        self._backend.update(self._marathonService, {self._socketpath: service})

    def _refresh(self):
        # Ensure the HAproxy load balancer is configured to proxy to the Marathon replicas
        self._connect()

        # Poll Marathon for running tasks
        logging.debug("GET Marathon services from %s", self._socketpath)
        response = unixrequest('GET', self._socketpath, '/v2/tasks', None, {'Accept': 'application/json'})
        self._backend.update(self, self._parse(response))
        logging.debug("Refreshed services from Marathon at %s", self._urls)

    def _parse(self, content):
        services = {}

        try:
            #logging.debug(content)
            document = json.loads(content)
        except ValueError, e:
            raise RuntimeError("Failed to parse HTTP JSON response from Marathon (%s): %s" % (str(e), str(content)[0:150]))

        def failed(check):
            alive = check.get('alive', False)
            if not alive:
                cause = check.get('lastFailureCause','')
                if cause:
                    logging.info("Task %s is failing health check with result '%s'", check.get('taskId',''), cause)
                else:
                    logging.debug("Skipping task %s which is not alive (yet)", check.get('taskId',''))
            return not alive

        for task in document.get('tasks', []):
            # Fetch exact config for this app version
            taskConfig = _getAppVersion(self._socketpath, task.get('appId'), task.get('version'))
            
            exposedPorts = task.get('ports', [])
            servicePorts = task.get('servicePorts', [])
            seenServicePorts = set()

            for servicePort, portIndex in zip(servicePorts, range(len(servicePorts))):
                protocol = 'tcp'
                key = '%s/%s' % (servicePort, protocol.lower())

                # Marathon returns multiple entries for services that expose both TCP and UDP using the same 
                # port number. There's no way to separate TCP and UDP service ports at the moment.
                if servicePort in seenServicePorts:
                    continue
                seenServicePorts.add(servicePort)

                # Verify that all health checks pass
                healthChecks = taskConfig.get('healthChecks', [])
                healthResults = task.get('healthCheckResults', [])
                
                if any(failed(check) for check in healthResults):
                    continue
                
                if len(healthResults) < len(healthChecks):
                    logging.debug("Skipping task %s which hasn't responded to health checks yet", task.get('id',''))
                    continue

                try:
                    exposedPort = exposedPorts[portIndex]

                    # Resolve hostnames since HAproxy wants IP addresses
                    ipaddr = socket.gethostbyname(task['host'])
                    server = Server(ipaddr, exposedPort)
                    
                    # Append backend to service
                    if key not in services:
                        name = '.'.join(reversed(filter(bool, task['appId'].split('/'))))
                        services[key] = Service(name, 'marathon:%s' % self._urls, servicePort, protocol)
                    services[key]._add(server)
                except Exception, e:
                    logging.warn("Failed parse service %s backend %s: %s", task.get('appId',''), task.get('id',''), str(e))
                    logging.debug(traceback.format_exc())
        
        return services
        
