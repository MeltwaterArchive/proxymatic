# ${service.name}:${service.port} (${service.source})
% if service.application == 'http':
http
% endif
% for server, i in zip(service.slots + [None] * (maxservers - len(service.slots)), range(maxservers)):
%   if server:
server ${i} address ${server.ip} port ${server.port} weight ${server.weight}${' max %s hard %s' % (server.maxconn, server.maxconn) if server.maxconn else ''}
%   else:
server ${i} address 0.0.0.0 port 0 weight 0 max 0 hard 0
%   endif
% endfor
