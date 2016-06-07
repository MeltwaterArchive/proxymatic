class AggregateDiscovery(object):
    def __init__(self):
        self._sources = []
    
    def add(self, source):
        self._sources.append(source)

    def isHealthy(self):
        for source in self._sources:
            if not source.isHealthy():
                return False
        
        return len(self._sources) > 0
