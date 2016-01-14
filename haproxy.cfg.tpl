# HAproxy configuration
#  - http://www.haproxy.org/download/1.5/doc/configuration.txt
#  - https://ymichael.com/2015/06/06/some-notes-playing-with-haproxy.html
global
  daemon
  
  # Log to syslog (enable when cluster supports log aggregation)
  #log 127.0.0.1 local0
  #log 127.0.0.1 local1 notice
  
  # Max total number of connections
  maxconn          ${int(maxconnections*2)}

  # Distribute the health checks with a bit of randomness
  spread-checks 5

defaults
  #log            global
  retries             3
  
  # Default per service max number of connections
  maxconn          ${maxconnections}

  # Timeout to establish a connection to the backend server
  timeout connect  5s

  # TCP connection timeout if no data is received from client
  timeout client   300s
  
  # TCP connection timeout if no data is received from server
  timeout server   300s

  # Timeout for WebSocket connections
  timeout tunnel   3600s

  # Timeout for health check
  timeout check    5s

% for service in services.values():
# ${service.name} (${service.source})
listen service-${service.portname}
% if service.protocol == 'unix':
  bind unix@${service.port}
% else:
  bind 0.0.0.0:${service.port}
% endif
  balance leastconn
  mode ${'http' if service.application == 'http' else 'tcp'}
% if service.healthcheck and service.application == 'http':
  option httpchk get ${service.healthcheckurl}
% endif
  default-server inter 15s
% 	for server, i in zip(service.slots, range(len(service.slots))):
%     if server:
  server backend-${service.portname}-${i} ${server.ip}:${server.port}${' check' if service.healthcheck else ''}
%     endif
% 	endfor  

% endfor
