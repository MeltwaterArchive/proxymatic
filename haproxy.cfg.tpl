# HAproxy configuration
#  - http://www.haproxy.org/download/1.5/doc/configuration.txt
#  - https://ymichael.com/2015/06/06/some-notes-playing-with-haproxy.html
global
  daemon
  
  # Log to syslog (enable when cluster supports log aggregation)
  #log 127.0.0.1 local0
  #log 127.0.0.1 local1 notice
  
  # Max total number of connections
  maxconn ${int(maxconnections*2)}

  # Distribute the health checks with a bit of randomness (value in percent of check interval)
  spread-checks 5

  # Limit the spread of checks, or services would take too long coming online (value in milliseconds)
  max-spread-checks 15000

defaults
  log global
  
  # Default per service max number of connections
  maxconn ${maxconnections}

  # Timeout to establish a connection to the backend server
  timeout connect 3s

  # TCP connection timeout if no data is received from client
  timeout client 300s
  
  # TCP connection timeout if no data is received from server
  timeout server 300s

  # Timeout for WebSocket connections
  timeout tunnel 3600s

  # Timeout for health check
  timeout check 5s

  # Timeout for requests waiting in a backend queue for a connection slot to open up
  timeout queue 30s

  # Timeout for receiving the full headers on a HTTP request
  timeout http-request 15s

  # Connection timeout waiting for a new request after a response has been sent
  timeout http-keep-alive 1s

  # Number of times to retry on TCP connect errors
  retries 3

  # Allow requests to be redispatched to other servers on TCP connect errors
  option redispatch

  # Add X-Forwarded-For headers if they're not already added by an upstream load balancer
  option forwardfor if-none

backend proxymatic
  # Offload proxymatic health check
  mode http
  option httpchk GET /status
  
  # Force HAproxy to read the response body to avoid "Broken pipe" errors in Python
  http-check expect string OK

  # Check Proxymatic status endpoint exposed on the unix socket
  server proxymatic unix@/tmp/proxymatic-status.sock check fall 3 rise 2 inter 1s

  # Rewrite the /_proxymatic_status url to /status for debugging reasons
  reqrep ^([^\ :]*)\ /_proxymatic_status(.*)     \1\ /status\2
  
% if statusendpoint:
frontend stats
  bind ${statusendpoint}
  mode http
  stats enable
  stats refresh 5s

  # Redirect to the stats URL
  acl is_root path /
  redirect code 301 location /haproxy?stats if is_root

  # Expose the Proxymatic status endpoint for debugging reasons
  acl proxymatic-status path /_proxymatic_status
  use_backend proxymatic if proxymatic-status

  # Offload the health check endpoint from proxymatic
  monitor-uri /status
  acl proxymatic_dead nbsrv(proxymatic) lt 1
  monitor fail if proxymatic_dead
% endif

% for service in services.values():
# ${service.name} (${service.source})
listen ${service.marathonpath}-${service.portname}
% if service.protocol == 'unix':
  bind unix@${service.port}
% else:
  bind 0.0.0.0:${service.port}
% endif
  balance leastconn
  mode ${'http' if service.application == 'http' else 'tcp'}
% if service.healthcheck and service.application == 'http':
  option httpchk GET ${service.healthcheckurl}
% endif
% if service.timeoutclient:
  timeout client ${service.timeoutclient}
% endif
% if service.timeoutserver:
  timeout server ${service.timeoutserver}
% endif
  default-server inter 15s
% 	for server in service.slots:
%     if server:
  server backend-${server.hostname}-${server.port} ${server.ip}:${server.port} weight ${int(float(server.weight) / 1000.0 * 256.0)}${' maxconn %s' % server.maxconn if server.maxconn else ''}${' check' if service.healthcheck else ''}
%     endif
% 	endfor  

% endfor
