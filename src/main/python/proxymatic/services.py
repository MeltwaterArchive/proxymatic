import re

class Server(object):
    def __init__(self, ip, port):
        self.ip = ip
        self.port = port
        
    def __cmp__(self, other):
        if not isinstance(other, Server):
            return -1
        return cmp((self.ip, self.port), (other.ip, other.port))
    
    def __hash__(self):
        return hash((self.ip, self.port))
    
    def __str__(self):
        return '%s:%s' % (self.ip, self.port)
        
    def __repr__(self):
        return 'Server(%s, %s)' % (repr(self.ip), repr(self.port))
    
class Service(object):
    def __init__(self, name, source, port, protocol):
        self.name = name
        self.source = source
        self.port = port
        self.protocol = protocol
        self.servers = set()
        self.slots = []
        
        # Check if there's a port override
        match = re.search('.@(\d+)$', self.name)
        if match:
            self.name = self.name[0:-(len(match.group(1))+1)]
            self.port = int(match.group(1))
        
    def __str__(self):
        return '%s:%s/%s -> [%s]' % (self.name, self.port, self.protocol, ', '.join([str(s) for s in self.servers]))

    def __repr__(self):
        return 'Service(%s, %s, %s)' % (repr(self.name), repr(self.port), repr(self.protocol), repr(self.servers))
        
    def __cmp__(self, other):
        if not isinstance(other, Service):
            return -1
        return cmp((self.name, self.port, self.protocol, self.servers), (other.name, other.port, other.protocol, other.servers))
    
    def __hash__(self):
        return hash((self.name, self.port, self.protocol, self.servers))
        
    def update(self, other):
        self.name = other.name
        self.source = other.source
        self.port = other.port
        self.protocol = other.protocol

        for server in self.servers - other.servers:
            self.remove(server)
        for server in other.servers - self.servers:
            self.add(server)
        
    def add(self, server):
        self.servers.add(server)
        
        # Keep servers in the same index when they're added
        for i in range(len(self.slots)):
            if not self.slots[i]:
                self.slots[i] = server
                return
        
        # No free slots, just append to end of list
        self.slots.append(server)
        
    def remove(self, server):
        self.servers.remove(server)
        
        # Set the server slot to None
        for i in range(len(self.slots)):
            if self.slots[i] == server:
                self.slots[i] = None
                return
        
        raise KeyError(str(server))
