import logging
from mako.template import Template
from proxymatic.util import *

class NginxBackend(object):
    def __init__(self, port, domain, proxyprotocol):
        self._port = port
        self._domain = domain
        self._proxyprotocol = proxyprotocol
        self._cfgfile = '/etc/nginx/conf.d/default.conf'
        
        # Render an empty default config without any vhosts since nginx won't start 
        # listening on port 80 unless the config is present at startup.
        self._render({})

        # Start the Nginx process
        shell('nginx')

    def update(self, source, services):
        seen = set()
            
        # Nginx only supports HTTP
        accepted = {}
        for key, service in services.items():
            if service.protocol == 'tcp' and service.name not in seen:
                accepted[key] = service
                seen.add(service.name)
        
        self._render(accepted)
        
        # Instruct Nginx to reload the config
        logging.debug("Reloaded the Nginx config '%s'", self._cfgfile)
        shell('nginx -s reload')
        #return accepted
        return {}

    def _render(self, accepted):
        # Expand the config template
        template = Template(filename='/etc/nginx/conf.d/default.conf.tpl')
        config = template.render(services=accepted, port=self._port, domain=self._domain, proxyprotocol=self._proxyprotocol)
        with open(self._cfgfile, 'w') as f:
            f.write(config)
        