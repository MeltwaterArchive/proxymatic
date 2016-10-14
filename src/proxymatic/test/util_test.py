import unittest
import proxymatic.util as util

class UtilTest(unittest.TestCase):
    def testRGet(self):
        self.assertEqual('c', util.rget({'a': [{'b': 'c'}]}, 'a', 0, 'b'))
        self.assertEqual(None, util.rget({'a': [{'b': 'c'}]}, 'a', 0, 'd'))
        self.assertEqual(None, util.rget({'a': [{'b': 'c'}]}, 'a', 1, 'b'))
        self.assertEqual(None, util.rget({'a': [{'b': 'c'}]}, 'a', -1, 'b'))
