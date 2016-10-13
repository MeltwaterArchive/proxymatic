import os
import random
import unittest
import tempfile
from mock import patch
from proxymatic.util import renderTemplate
from proxymatic.services import Service, Server
from proxymatic.backend.haproxy import HAProxyBackend

class HAproxyTest(unittest.TestCase):
    def testHAProxyReload(self):
        """
        Verifies that the HAproxy process is reloaded gracefully
        """
        services = {
            '1234/tcp': Service('example.demo', self, 1234, 'tcp').
            addServer(Server('1.2.3.4', 31001, 'worker1'))
        }

        expected = """# example.demo (testHAProxyReload (proxymatic.test.haproxy_test.HAproxyTest))
listen demo.example-1234
  bind 0.0.0.0:1234
  balance leastconn
  mode tcp
  default-server inter 15s
  server backend-worker1-31001 1.2.3.4:31001 weight 128
"""
        self._check(services, expected)

        services = {
            '1234/tcp': Service('example.demo', self, 1234, 'tcp').
            addServer(Server('1.2.3.4', 31001, 'worker1')).
            addServer(Server('2.2.3.4', 31002, 'worker2'))
        }

        expected = """# example.demo (testHAProxyReload (proxymatic.test.haproxy_test.HAproxyTest))
listen demo.example-1234
  bind 0.0.0.0:1234
  balance leastconn
  mode tcp
  default-server inter 15s
  server backend-worker1-31001 1.2.3.4:31001 weight 128
  server backend-worker2-31002 2.2.3.4:31002 weight 128
"""
        self._check(services, expected, pid=567)

    def testWeight(self):
        """
        Verifies that backend weights are processed correctly
        """
        services = {
            '1234/tcp': Service('example.demo', self, 1234, 'tcp').
            addServer(Server('1.2.3.4', 31001, 'worker1').setWeight(250)).
            addServer(Server('2.2.3.4', 31002, 'worker2'))
        }

        expected = """# example.demo (testWeight (proxymatic.test.haproxy_test.HAproxyTest))
listen demo.example-1234
  bind 0.0.0.0:1234
  balance leastconn
  mode tcp
  default-server inter 15s
  server backend-worker1-31001 1.2.3.4:31001 weight 64
  server backend-worker2-31002 2.2.3.4:31002 weight 128
"""
        self._check(services, expected)

    def testLoadBalancerMode(self):
        """
        Verifies that HTTP mode can be enabled
        """
        services = {
            '1234/tcp': Service('example.demo', self, 1234, 'tcp').
            setApplication('http').
            addServer(Server('1.2.3.4', 31001, 'worker1'))
        }

        expected = """# example.demo (testLoadBalancerMode (proxymatic.test.haproxy_test.HAproxyTest))
listen demo.example-1234
  bind 0.0.0.0:1234
  balance leastconn
  mode http
  default-server inter 15s
  server backend-worker1-31001 1.2.3.4:31001 weight 128
"""
        self._check(services, expected)

    def _check(self, services, expected, pid=None):
        """
        Dummy reload of HAproxy and verifies that the rendered config contains the expected fragment
        """
        scope = {'rendered': None, 'count': 0}
        random.seed(0)

        def render(src, dst, *args, **kwargs):
            if src == '/etc/haproxy/haproxy.cfg.tpl' and not os.path.exists('/etc/haproxy/haproxy.cfg.tpl'):
                src = os.path.dirname(__file__) + '/../../../haproxy.cfg.tpl'

            scope['rendered'] = renderTemplate(src, '/dev/null', *args, **kwargs)
            scope['count'] += 1
            return scope['rendered']

        with patch('proxymatic.util.shell') as shell_mock:
            # Write out the pid
            if pid:
                tmpfile = tempfile.NamedTemporaryFile()
                pidfile = tmpfile.name
                with open(pidfile, 'w') as pd:
                    pd.write(str(pid))
            else:
                pidfile = '/tmp/proxymatic-haproxy-test.pid'

            # Render the config
            with patch('proxymatic.util.renderTemplate', wraps=render):
                backend = HAProxyBackend(8092, '0.0.0.0:9090', pidfile)
                backend.update(self, services)

                try:
                    self.assertIn(expected, scope['rendered'])
                    self.assertEquals(2, scope['count'])
                except:
                    print scope['rendered']
                    raise

            # Check that HAproxy was reloaded correctly
            command = 'haproxy -f /etc/haproxy/haproxy.cfg -p ' + pidfile
            if pid:
                command += ' -sf %s' % pid
            self.assertIn(command, shell_mock.call_args[0][0])
