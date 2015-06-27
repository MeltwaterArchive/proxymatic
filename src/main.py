#!/bin/env python
import os, sys, optparse, logging, time, subprocess
from urlparse import urlparse
from pprint import pprint
from proxymatic.discovery.marathon import MarathonDiscovery
from proxymatic.discovery.registrator import RegistratorEtcdDiscovery
from proxymatic.backend.aggregate import AggregateBackend
from proxymatic.backend.haproxy import HAProxyBackend
from proxymatic.backend.nginx import NginxBackend
from proxymatic.backend.pen import PenBackend

parser = optparse.OptionParser(
    usage='docker run meltwater/proxymatic:latest [options]...',
    description='Proxy for TCP/UDP services registered in Marathon and etcd')

def parsebool(value):
    truevals = set(['true', '1'])
    falsevals = set(['false', '0'])
    stripped = str(value).lower().strip()
    if stripped in truevals:
        return True
    if stripped in falsevals:
        return False
    
    logging.error("Invalid boolean value '%s'", value)
    sys.exit(1)

def parseint(value):
    try:
        return int(value)
    except:
        logging.error("Invalid integer value '%s'", value)
        sys.exit(1)

parser.add_option('-r', '--registrator', dest='registrator', help='URL where registrator publishes services, e.g. "etcd://etcd-host:4001/services"',
    default=os.environ.get('REGISTRATOR_URL', None))
        
parser.add_option('-m', '--marathon', dest='marathon', help='Marathon URL to query, e.g. "http://marathon-host:8080/"',
    default=os.environ.get('MARATHON_URL', None))
parser.add_option('-c', '--marathon-callback', dest='callback', help='URL to listen for Marathon HTTP callbacks, e.g. "http://`hostname -f`:5090/"',
    default=os.environ.get('MARATHON_CALLBACK_URL', None))
    
parser.add_option('-i', '--refresh-interval', dest='interval', help='Polling interval in seconds when using non-event capable backends [default: %default]',
    type="int", default=parseint(os.environ.get('REFRESH_INTERVAL', '60')))
parser.add_option('-e', '--expose-host', dest='exposehost', help='Expose services running in net=host mode. May cause port collisions when this container is also run in net=host mode on the same machine [default: %default]',
    action="store_true", default=parsebool(os.environ.get('EXPOSE_HOST', False)))

parser.add_option('--pen-servers', dest='penservers', help='Max number of backend servers for each pen service [default: %default]',
    type="int", default=parseint(os.environ.get('PEN_SERVERS', '32')))
parser.add_option('--pen-clients', dest='penclients', help='Max number of pen client connections [default: %default]',
    type="int", default=parseint(os.environ.get('PEN_CLIENTS', '8192')))
    
parser.add_option('--haproxy', dest='haproxy', help='Use HAproxy for TCP services instead of running everything through Pen [default: %default]',
    action="store_true", default=parsebool(os.environ.get('HAPROXY', False)))

parser.add_option('--vhost-domain', dest='vhostdomain', help='Domain to add service virtual host under, e.g. "app.example.com"',
    default=os.environ.get('VHOST_DOMAIN', None))
parser.add_option('--proxy-protocol', dest='proxyprotocol', help='Enable proxy protocol on the nginx vhost [default: %default]',
    action="store_true", default=parsebool(os.environ.get('PROXY_PROTOCOL', False)))

parser.add_option('-v', '--verbose', dest='verbose', help='Increase logging verbosity',
    action="store_true", default=parsebool(os.environ.get('VERBOSE', False)))

(options, args) = parser.parse_args()

if options.verbose:
    logging.getLogger().setLevel(logging.DEBUG)
else:
    logging.getLogger().setLevel(logging.INFO)

if not options.registrator and not options.marathon:
    parser.print_help()
    sys.exit(1)

# Fetch port to listen for Marathon callbacks
callbackport = None
if options.callback:
	callbackurl = urlparse(options.callback)
	callbackport = callbackurl.port or 80
backend = AggregateBackend(options.exposehost, set([callbackport]))

if options.vhostdomain:
    subprocess.call('nginx', shell=True)
    backend.add(NginxBackend(options.vhostdomain, options.proxyprotocol))

if options.haproxy:
    subprocess.call('haproxy -f /etc/haproxy/haproxy.cfg -p /run/haproxy.pid', shell=True)
    backend.add(HAProxyBackend())

# Pen is needed for UDP support so always add it
backend.add(PenBackend(options.penservers, options.penclients))
 
if options.registrator:
    registrator = RegistratorEtcdDiscovery(backend, options.registrator)
    registrator.start()

if options.marathon:
    marathon = MarathonDiscovery(backend, str(options.marathon).rstrip('/'), options.callback, options.interval)
    marathon.start()

# Loop forever and allow the threads to work. Setting the threads to daemon=False and returning 
# from the main thread seems to prevent Ctrl+C/SIGTERM from terminating the process properly.
while True:
    time.sleep(60)
