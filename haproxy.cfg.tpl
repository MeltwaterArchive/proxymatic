# HAproxy configuration
#  - http://www.haproxy.org/download/1.5/doc/configuration.txt
global
  daemon
  
  # Log to syslog (enable when cluster supports log aggregation)
  #log 127.0.0.1 local0
  #log 127.0.0.1 local1 notice
  
  # Max total number of connections
  maxconn          4096

defaults
  #log            global
  retries             3
  
  # Default per service max number of connections
  maxconn          2000

  # Timeout to establish a connection to the backend server
  timeout connect    5s
  
  # TCP connection timeout if no data is received from client
  timeout client   300s
  
  # TCP connection timeout if no data is received from server
  timeout server   300s

listen stats
  bind 127.0.0.1:9090
  balance
  mode http
  stats enable
  stats auth admin:admin

% for service in services.values():
# ${service.name} (${service.source})
listen service-${service.portname}
% if service.protocol == 'unix':
  bind unix@${service.port}
% else:
  bind 0.0.0.0:${service.port}
% endif
  mode tcp
  #option tcplog
  balance leastconn
% 	for server, i in zip(service.slots, range(len(service.slots))):
%     if server:
  server backend-${service.portname}-${i} ${server.ip}:${server.port} check
%     endif
% 	endfor  

% endfor
