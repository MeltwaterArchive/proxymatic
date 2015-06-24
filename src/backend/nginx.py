import logging, subprocess
from mako.template import Template
from proxymatic.util import *

class NginxBackend(object):
    def __init__(self, domain):
        self._domain = domain
    
    def update(self, source, services):
        cfgfile = '/etc/nginx/conf.d/default.conf'
        seen = set()
            
        # Nginx only supports HTTP
        accepted = {}
        for key, service in services.items():
            if service.protocol == 'tcp' and service.name not in seen:
                accepted[key] = service
                seen.add(service.name)
        
        # Expand the config template
        template = Template(filename='/etc/nginx/conf.d/default.conf.tpl')
        config = template.render(services=accepted, domain=self._domain)
        with open(cfgfile, 'w') as f:
            f.write(config)
        
        # Instruct Nginx to reload the config
        logging.debug("Reloaded the Nginx config '%s'", cfgfile)
        subprocess.call('nginx -s reload', shell=True)
        #return accepted
        return {}
