import logging, socket, time, urllib2, json
from urllib import urlencode
from urlparse import urlparse
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from proxymatic.services import Server, Service
from proxymatic.util import *

class MarathonDiscovery(object):
    def __init__(self, backend, url, callback, interval):
        self._backend = backend
        self._url = url
        self._callback = callback
        self._interval = interval
        self.priority = 10
        
    def start(self):
        marathon = self
        
        if marathon._callback:
            # Start a HTTP server that listens for callbacks from Marathon
            class CallbackHandler(BaseHTTPRequestHandler):
                def do_POST(self):
                    logging.info("Received HTTP callback from Marathon")
                    marathon._refresh()
            
            callbackurl = urlparse(marathon._callback)
            server = HTTPServer(('', callbackurl.port or 80), CallbackHandler)
            server.timeout = marathon._interval
            run(server.serve_forever, "Error processing Marathon HTTP callback from '" + str(marathon._url) + "': %s")

            def register():
                # Subscribe to Marathon events
                response = post('%s/v2/eventSubscriptions?%s' % (marathon._url, urlencode({'callbackUrl': marathon._callback}))).read()
                logging.info("Registered Marathon HTTP callback with %s", marathon._url)
                time.sleep(marathon._interval)
            run(register, "Error registering Marathon HTTP callback with '" + str(self._url) + "': %s")

        # Run refresh() in thread with retry on error
        def refresh():
            marathon._refresh()
            time.sleep(marathon._interval)
        run(refresh, "Marathon error from '" + str(self._url) + "/v2/tasks': %s")
        
    def _refresh(self):
        url = '%s/v2/tasks' % self._url
        logging.debug("GET Marathon services from %s", url)
        request = urllib2.Request(url, None, {'Accept': 'application/json'})
        response = urllib2.urlopen(request)
        services = self._parse(response.read())
        self._backend.update(self, services)
        logging.info("Refreshed services from Marathon at %s", self._url)
        
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
                        services[key] = Service(name, 'marathon:%s' % self._url, servicePort, protocol)
                    services[key]._add(server)
                except Exception, e:
                    logging.warn("Failed parse service %s backend %s: %s", task.get('appId',''), task.get('id',''), str(e))
                    logging.debug(traceback.format_exc())
        
        return services
        
