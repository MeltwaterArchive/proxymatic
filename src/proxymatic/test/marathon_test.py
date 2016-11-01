import os
import random
import unittest
from mock import patch
from proxymatic.discovery.marathon import MarathonDiscovery, getAppVersion

def fileserver(path):
    counts = {}

    def handler(method, socketpath, url, body=None, headers={}):
        # Try to read response for this sequence number
        filename = '%s%s_%s.json' % (path, url.replace('/', '_'), counts.get(url, 0))
        if not os.path.exists(filename):
            filename = '%s%s.json' % (path, url.replace('/', '_'))
        counts[url] = counts.get(url, 0) + 1

        if method == 'GET':
            if os.path.exists(filename):
                return open(filename).read()
            raise ValueError("Unknown test HTTP endpoint %s (expected test file %s)" % (url, filename))

        raise ValueError("Unsupported HTTP method %s" % method)

    return handler

class TestBackend(object):
    def __init__(self):
        self.source = None
        self.services = {}
        self.updatedCount = 0

    def update(self, source, services):
        self.source = source
        self.services = services
        self.updatedCount += 1

class MarathonTest(unittest.TestCase):
    def setUp(self):
        # Clear the response cache to avoid interference between tests
        getAppVersion.cache_clear()
        random.seed(0)

    def testMarathonLoadBalancer(self):
        backend = TestBackend()
        MarathonDiscovery(backend, ['http://1.2.3.4:8080/', 'http://1.2.3.5:8080/'], 15)
        self.assertEquals(1, backend.updatedCount)
        self.assertEquals(
            "marathon:/tmp/marathon.sock/http -> [1.2.3.4:8080, 1.2.3.5:8080]",
            str(backend.services['/tmp/marathon.sock']))

    @patch('proxymatic.util.unixrequest', wraps=fileserver(os.path.dirname(__file__) + '/marathon/testRefresh/'))
    def testRefresh(self, unixrequest_mock):
        backend = TestBackend()
        discovery = MarathonDiscovery(backend, ['http://1.2.3.4:8080/'], 15)

        discovery._refresh()
        self.assertEquals(2, backend.updatedCount)
        self.assertEquals(
            "webapp.demo:1234/tcp -> [127.0.0.1:31478]",
            str(backend.services['1234/tcp']))

        discovery._refresh()
        self.assertEquals(3, backend.updatedCount)
        self.assertEquals(
            "webapp.demo:1234/tcp -> [127.0.0.1:31478, 127.0.0.1:31479]",
            str(backend.services['1234/tcp']))

    @patch('proxymatic.util.unixrequest', wraps=fileserver(os.path.dirname(__file__) + '/marathon/testCanary/'))
    def testCanary(self, unixrequest_mock):
        backend = TestBackend()
        discovery = MarathonDiscovery(backend, ['http://1.2.3.4:8080/'], 15)

        discovery._refresh()
        self.assertEquals(2, backend.updatedCount)
        self.assertEquals(
            "webapp.demo:1234/http -> [127.0.0.1:31468, 127.0.0.1:31469(weight=100)]",
            str(backend.services['1234/tcp']))

    @patch('proxymatic.util.unixrequest', wraps=fileserver(os.path.dirname(__file__) + '/marathon/testLoadBalancerOptions/'))
    def testLoadBalancerOptions(self, unixrequest_mock):
        backend = TestBackend()
        discovery = MarathonDiscovery(backend, ['http://1.2.3.4:8080/'], 15)

        discovery._refresh()
        self.assertEquals(2, backend.updatedCount)
        self.assertEquals(
            "webapp.demo:1234/http -> [127.0.0.1:31468(weight=100,maxconn=150), 127.0.0.1:31469]",
            str(backend.services['1234/tcp']))
