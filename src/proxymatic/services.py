import re
from copy import copy
from random import randint

class Server(object):
    def __init__(self, ip, port, hostname):
        self.ip = ip
        self.port = port
        self.hostname = hostname
        self.weight = 500

    def __cmp__(self, other):
        if not isinstance(other, Server):
            return -1
        return cmp((self.ip, self.port), (other.ip, other.port))

    def __hash__(self):
        return hash((self.ip, self.port))

    def __str__(self):
        result = '%s:%s' % (self.ip, self.port)
        if self.weight != 500:
            result += "(%d)" % self.weight
        return result

    def __repr__(self):
        return 'Server(%s, %s, %s)' % (repr(self.ip), repr(self.port), repr(self.weight))

    def clone(self):
        return copy(self)

    def setWeight(self, weight):
        clone = self.clone()
        clone.weight = weight
        return clone

class Service(object):
    def __init__(self, name, source, port, protocol, application='binary', healthcheck=False, healthcheckurl='/'):
        self.name = name
        self.source = source
        self.port = port
        self.protocol = protocol
        self.application = application
        self.healthcheck = healthcheck
        self.healthcheckurl = healthcheckurl
        self.servers = set()
        self.slots = []

        # Check if there's a port override
        match = re.search('.@(\d+)$', self.name)
        if match:
            self.name = self.name[0:-(len(match.group(1))+1)]
            self.port = int(match.group(1))

    def clone(self):
        clone = Service(self.name, self.source, self.port, self.protocol, self.application, self.healthcheck, self.healthcheckurl)
        clone.servers = set(self.servers)
        clone.slots = list(self.slots)
        return clone

    def __str__(self):
        return '%s:%s/%s -> [%s]' % (
            self.name, self.port, self.application if self.application != 'binary' else self.protocol,
            ', '.join([str(s) for s in self.servers]))

    def __repr__(self):
        return 'Service(%s, %s, %s, %s, %s)' % (repr(self.name), repr(self.port), repr(self.protocol), repr(self.application), repr(self.servers))

    def __cmp__(self, other):
        if not isinstance(other, Service):
            return -1
        return cmp((self.name, self.port, self.protocol, self.servers), (other.name, other.port, other.protocol, other.servers))

    def __hash__(self):
        return hash((self.name, self.port, self.protocol, self.servers))

    @property
    def portname(self):
        return re.sub('[^a-zA-Z0-9]', '_', str(self.port))

    @property
    def marathonpath(self):
        ret = ''
        for s in self.name.split('.'):
            if ret is not '':
                ret = s + '.' + ret
            else:
                ret = s
        return ret

    def update(self, other):
        """
        Returns an new updated Service object
        """
        clone = self.clone()
        clone.name = other.name
        clone.source = other.source
        clone.port = other.port
        clone.protocol = other.protocol

        for server in clone.servers - other.servers:
            clone._remove(server)

        for server in other.servers - clone.servers:
            clone._add(server)

        return clone

    def addServer(self, server):
        clone = self.clone()
        clone._add(server)
        return clone

    def setApplication(self, application):
        clone = self.clone()
        clone.application = application
        return clone

    def _add(self, server):
        self.servers.add(server)

        # Keep servers in the same index when they're added
        for i in range(len(self.slots)):
            if not self.slots[i]:
                self.slots[i] = server
                return

        # Not present in list, just insert randomly
        self.slots.insert(randint(0, len(self.slots)), server)

    def _remove(self, server):
        self.servers.remove(server)

        # Set the server slot to None
        for i in range(len(self.slots)):
            if self.slots[i] == server:
                del self.slots[i]
                return

        raise KeyError(str(server))
