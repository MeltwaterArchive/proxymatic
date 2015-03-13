import logging, subprocess
from mako.template import Template

class HAProxyBackend(object):
    def __init__(self, reload, cfgtemplate, target):
        self._reload = reload
        self._cfgtemplate = cfgtemplate
        self._target = target
        
    def update(self, source, services):
        # HAproxy only supports TCP
        accepted = {}
        for key, service in services.items():
            if service.protocol == 'tcp':
                accepted[key] = service
        
        # Expand the config template
        template = Template(filename=self._cfgtemplate)
        config = template.render(services=accepted, mangle=mangle)
        with open(self._target, 'w') as f:
            f.write(config)
        
        # Instruct HAproxy to reload the config
        subprocess.call(self._reload, shell=True)
        return accepted
