import logging, socket, time, urllib2
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
        request = urllib2.Request(url, None, {'Accept': 'text/plain'})
        response = urllib2.urlopen(request)
        services = self._parse(response.read())
        self._backend.update(self, services)
        logging.info("Refreshed services from Marathon at %s", self._url)
        
    def _parse(self, content):
        services = {}

        logging.debug(content)

        # Marathon returns one line per service port like
        #  <service-id> [<service-port>] [<task-ip>:<task-port>)]...
        for line in content.split("\n"):
            # Split on tabs and filter empty parts
            parts = [str(part) for part in line.split("\t") if len(part) > 0]

            # Some service may not have service port and/or active tasks
            if len(parts) < 3 or not parts[1].isdigit():
                continue

            # Marathon returns multiple entries for services that expose both TCP and UDP using the same 
            # port number. There's no way to separate TCP and UDP service ports at the moment.
            port = int(parts[1])
            protocol = 'tcp'
            key = '%s/%s' % (port, protocol.lower())
            if key in services:
                continue
            
            # Parse service backends
            for backend in parts[2:]:
                try:
                    # Resolve hostnames since HAproxy wants IP addresses
                    endpoint = backend.split(':')
                    ipaddr = socket.gethostbyname(endpoint[0])
                    server = Server(ipaddr, endpoint[1])
                    
                    # Append backend to service
                    if key not in services:
                        name = '.'.join(reversed(parts[0].split('_')))
                        services[key] = Service(name, 'marathon:%s' % self._url, port, protocol)
                    services[key]._add(server)
                except Exception, e:
                    logging.warn("Failed parse service %s backend %s: %s", parts[0], backend, str(e))
                    logging.debug(traceback.format_exc())
        
        return services
        
