import unittest
import sys
from proxymatic.test.util_test import UtilTest

if __name__ == '__main__':
    suite = unittest.TestSuite()

    suite.addTest(unittest.makeSuite(UtilTest))

    res = not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()

    sys.exit(res)
