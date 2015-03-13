# ${service.name}:${service.port} (${service.source})
% for server, i in zip(service.slots + [None] * (maxservers - len(service.slots)), range(maxservers)):
%   if server:
server ${i} address ${server.ip} port ${server.port}
%   else:
server ${i} address 0.0.0.0 port 0
%   endif
% endfor
