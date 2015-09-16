import logging, subprocess
from mako.template import Template
from proxymatic.util import *

class HAProxyBackend(object):
    def __init__(self):
        subprocess.call('haproxy -f /etc/haproxy/haproxy.cfg -p /run/haproxy.pid', shell=True)

    def update(self, source, services):
        # HAproxy only supports TCP
        accepted = {}
        for key, service in services.items():
            if service.protocol == 'tcp' or service.protocol == 'unix':
                accepted[key] = service
        
        # Expand the config template
        template = Template(filename='/etc/haproxy/haproxy.cfg.tpl')
        config = template.render(services=accepted)
        with open('/etc/haproxy/haproxy.cfg', 'w') as f:
            f.write(config)
        
        # Instruct HAproxy to reload the config
        subprocess.call('haproxy -f /etc/haproxy/haproxy.cfg -p /run/haproxy.pid -sf $(cat /run/haproxy.pid)', shell=True)
        return accepted
