import unittest
from proxymatic.services import Server

class ServicesTest(unittest.TestCase):
    def testServerCmp(self):
        server = Server('127.0.0.1', 5432, 'localhost')
        self.assertEqual(server, server.clone())
        self.assertEqual(server.setWeight(250), server.setWeight(250).clone())
        self.assertNotEqual(server, server.setWeight(250))
        self.assertNotEqual(server, server.setMaxconn(150))
