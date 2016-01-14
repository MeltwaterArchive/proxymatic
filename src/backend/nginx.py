import logging
from proxymatic.util import *

def precedence(service, prev):
    return service.port < prev.port

class NginxBackend(object):
    def __init__(self, port, domain, proxyprotocol, maxconnections):
        self._port = port
        self._domain = domain
        self._proxyprotocol = proxyprotocol
        self._maxconnections = maxconnections
        self._prev = {}
        self._cfgfile = '/etc/nginx/nginx.conf'
        
        # Render an empty default config without any vhosts since nginx won't start 
        # listening on port 80 unless the config is present at startup.
        self._render({})

        # Start the Nginx process
        shell('nginx')

    def update(self, source, services):
        accepted = {}
            
        # Nginx only supports HTTP
        for key, service in services.items():
            if service.protocol == 'tcp' and (service.name not in accepted or precedence(service, accepted[service.name])):
                accepted[service.name] = service

        # Check if anything has changed
        if self._prev != accepted:
            self._render(accepted)

            # Instruct Nginx to reload the config
            logging.debug("Reloaded the Nginx config '%s'", self._cfgfile)
            shell('nginx -s reload')
            self._prev = accepted

        return {}

    def _render(self, accepted):
        # Expand the config template
        renderTemplate('/etc/nginx/nginx.conf.tpl', self._cfgfile, {
            'services': accepted, 
            'port': self._port, 
            'domain': self._domain, 
            'proxyprotocol': self._proxyprotocol, 
            'maxconnections': self._maxconnections})
