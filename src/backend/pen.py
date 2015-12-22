import os, logging
from proxymatic.util import *

class PenBackend(object):
    def __init__(self, maxconnections, maxservers, maxclients):
        self._maxconnections = maxconnections
        self._maxservers = maxservers
        self._maxclients = maxclients
        self._state = {}
        
    def update(self, source, services):
        state = {}
        accepted = {}
    
        # Create new proxy instances
        for key, service in services.items():
            if service.protocol == 'tcp' or service.protocol == 'udp':
                statekey = (service.port, service.protocol)
                prev = self._state.get(statekey, None)
                next = self._ensure(service, prev)
                state[statekey] = next
                accepted[key] = service
        
        # Kill any proxy instances that are no longer relevant
        for key, prev in self._state.items():
            if key not in state:
                kill(prev['pidfile'])

        self._state = state
        return accepted
    
    def _ensure(self, service, prev):
        """
        Ensures that there's a pen proxy running for the given service
        """
        # Check for an existing instance
        if prev and prev['servers'] == set(service.servers) and alive(prev['pidfile']):
            return prev

        # Parameters for starting pen
        filename = 'pen-%s-%s' % (service.portname, service.protocol)
        cfgfile = '/tmp/%s.cfg' % filename
        pidfile = '/tmp/%s.pid' % filename
        ctlfile = '/tmp/%s.ctl' % filename
        cmd = [
            'pen', 'pen',
            '-r', # Disable sticky sessions
            '-W', # Use weight/least-connected balancing mode
            '-u', 'pen',
            '-x', str(self._maxconnections),
            '-c', str(self._maxclients), 
            '-S', str(self._maxservers), 
            '-F', cfgfile, 
            '-p', pidfile,
            '-C', ctlfile]
        
        if service.protocol == 'udp':
            cmd.append('-U')
        cmd.append(str(service.port))
        
        next = {
            'pidfile': pidfile,
            'servers': set(service.servers)}
        
        # Write the configuration file
        renderTemplate('/etc/pen/pen.cfg.tpl', cfgfile, {'service': service, 'maxservers': self._maxservers})

        # Try to reload (SIGHUP) an existing pen
        if prev and kill(prev['pidfile'], signal.SIGHUP):
            logging.debug("Reloaded the pen config '%s'", cfgfile)
        else:
            # Kill any unresponsive existing process 
            if prev:
                kill(prev['pidfile'])
            
            # Start the pen process, it forks and runs in the background
            os.spawnlp(os.P_WAIT, *cmd)
            logging.debug("Started pen with config '%s'", cfgfile)
        
        return next
