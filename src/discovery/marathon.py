import logging, socket, time, urllib2, json
from urllib import urlencode
from urlparse import urlparse
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from proxymatic.services import Server, Service
from proxymatic.util import *

class MarathonDiscovery(object):
    def __init__(self, backend, urls, callback, interval):
        self._backend = backend
        self._urls = [url.rstrip('/') for url in urls]
        self._socketpath = '/tmp/marathon.sock'
        self._callback = callback
        self._interval = interval
        self.priority = 10

    def start(self):
        marathon = self
        
        if marathon._callback:
            # Start a HTTP server that listens for callbacks from Marathon
            class CallbackHandler(BaseHTTPRequestHandler):
                def do_POST(self):
                    logging.debug("Received HTTP callback from Marathon")
                    marathon._refresh()
            
            callbackurl = urlparse(marathon._callback)
            server = HTTPServer(('', callbackurl.port or 80), CallbackHandler)
            server.timeout = marathon._interval
            run(server.serve_forever, "Error processing Marathon HTTP callback from '" + str(marathon._urls) + "': %s")

            def register():
                # Subscribe to Marathon events
                response = unixrequest('POST', self._socketpath, '/v2/eventSubscriptions?%s' % urlencode({'callbackUrl': marathon._callback}))
                logging.debug("Registered Marathon HTTP callback with %s", marathon._urls)
                time.sleep(marathon._interval)
            run(register, "Error registering Marathon HTTP callback with '" + str(self._urls) + "': %s")

        # Run refresh() in thread with retry on error
        def refresh():
            marathon._refresh()
            time.sleep(marathon._interval)
        run(refresh, "Marathon error from '" + str(self._urls) + "/v2/tasks': %s")
        
    def _refresh(self):
        services = {}

        # Start the local load balancer in front of Marathon
        service = Service('marathon.local', 'marathon:%s' % self._urls, self._socketpath, 'unix')
        services[self._socketpath] = service

        for url in self._urls:
            parsed = urlparse(url)

            # Resolve hostnames since HAproxy wants IP addresses
            ipaddr = socket.gethostbyname(parsed.hostname or '127.0.0.1')
            server = Server(ipaddr, parsed.port or 80)
            service._add(server)

        # Poll Marathon for running tasks
        try:
            logging.debug("GET Marathon services from %s", self._socketpath)
            response = unixrequest('GET', self._socketpath, '/v2/tasks', None, {'Accept': 'application/json'})
            services.update(self._parse(response))
        finally:
            self._backend.update(self, services)
        logging.debug("Refreshed services from Marathon at %s", self._urls)
        
    def _parse(self, content):
        logging.debug(content)

        services = {}
        document = json.loads(content)

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
                if any(failed(check) for check in task.get('healthCheckResults',[])):
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
        
